#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import itertools
from os import listdir
from os.path import isfile, join
import sys
import time

import pandas as pd

import numpy as np

from scipy.stats import kurtosis, skew

from sklearn.metrics import classification_report, f1_score, confusion_matrix

import seaborn as sns
import matplotlib.pyplot as plt 

from encrypted_traffic_classification import EncryptedTrafficClassifier, EncryptedTrafficClassifierIterator

filename_patterns = { 
    "youtube_": "STREAMING",
    "Google_Play_Music_": "Google_Play_Music",
    "GoogleHangout_VoIP_": "GoogleHangout_VoIP",
    "GoogleHangout_Chat_": "GoogleHangout_Chat",
    "FileTransfer_": "FileTransfer",    
}

########################################
# Data preparation: convert RAW data
########################################
class NetFlowQUICClassifier(EncryptedTrafficClassifier):
    def __init__(self, nb_folds, nb_packets_per_flow):        
        super().__init__(
            nb_folds= nb_folds,
            nb_packets_per_flow = nb_packets_per_flow,
            filename_prefix = "netflow_quic",
            processed_data_output_dir = "netflow_quic_output/",
            data_dir = "data/Netflow-QUIC/"            
        )
                
        pools = [tuple(pool) for pool in [self.nb_packets_per_flow, range(self.nb_folds)]]
        result = [[]]
        for pool in pools:
            result = [x+[y] for x in result for y in pool]
        self.flow_ids = result

        pools = [tuple(pool) for pool in [self.nb_packets_per_flow]]
        result = [[]]
        for pool in pools:
            result = [x+[y] for x in result for y in pool]
        self.flow_ids_without_folds = result

        pools = [tuple(pool) for pool in [range(self.nb_folds)]]
        result = [[]]
        for pool in pools:
            result = [x+[y] for x in result for y in pool]
        self.packet_ids = result
        
    ########################################
    # Preprocessing
    ########################################
    def _get_flows_with_all_packets(self):
        print("_get_flows_with_all_packets")
        df_flows = {}
        start_time = time.time()
        nb_flows = 0
        df_flows = pd.DataFrame()
        self.classes = set()
        files = [f for f in listdir(self.data_dir) if isfile(join(self.data_dir, f))]
        for _i in range(len(files)):
            f = self.data_dir + "/" + files[_i]
            print("f=", f)
            start_time = time.time()
            df_new = pd.read_csv(f, 
                                 names = [
                                     'packet_id',
                                     'timestamp', 
                                     'iat',                                                         
                                     'source',
                                     'sport',
                                     'dest', 
                                     'dport',
                                     'protocol', 
                                     'length',
                                     'flow_id'
                                 ],
                                 dtype = {
                                     'flow_id': 'Int32',
                                     'timestamp': np.float64, 
                                     'iat': np.float64,                                                         
                                     'source':str,
                                     'sport': 'Int32',
                                     'dest': str, 
                                     'dport': 'Int32',
                                     'protocol': 'Int32',
                                     'length': 'Int64',
                                     'flow_id': 'Int64'
                                 },
                                 header = 0
                                 )   
            print(f, df_new.shape)
            
            # drop DNS traffic
            df_new = df_new.drop(df_new[df_new['sport'] == 53].index)
            df_new = df_new.drop(df_new[df_new['dport'] == 53].index)
            
            found = False
            for k, v in filename_patterns.items():
                if k in f:
                    df_new['class'] = v
                    self.classes.add(v)
                    found = True
                    break
            if found == False:
                print("Type for file", f, "not found")
                sys.exit(1)
            dfs = []
            # extract flow and add statistical features
            for flow_id in df_new['flow_id'].unique():                    
                nb_flows += 1
                df_new = df_new.sort_values(by = ['packet_id'])
                d = df_new[df_new['flow_id'] == flow_id].head(n = 1)
                d['nb_packets'] = len(df_new[df_new['flow_id'] == flow_id])
                c = d['class'].tolist()
                dport = d.dport.tolist()
                sport = d.sport.tolist()
                #print(d)
                _df = df_new.loc[df_new['flow_id'] == flow_id, 'iat']
                d['sum_iat'] = np.sum(_df)
                
                _df = df_new.loc[df_new['flow_id'] == flow_id, 'length']
                d['sum_length'] = np.sum(_df)
                dfs.append(d)
            _d = pd.concat(dfs)
            df_flows = pd.concat([_d, df_flows])

            print(f, "processed in ", time.time() - start_time, "seconds.")            
            
            # uncomment following line to stop after the first file during debug
            # break
                
        print("  processing took ", time.time() - start_time, "seconds.")
        print("%d flows processed" % nb_flows)            
        # Finish processing the data, create the train/tests split and save as pickle files
        df_flows = df_flows.fillna(0)
        
        self.classes = list(self.classes)
        self._hotencode_class(df_flows)
        return df_flows
    
    def data_preparation(self):
        print("data_preparation")
        import warnings
        warnings.filterwarnings("ignore")

        df_flows = {}
        files = [f for f in listdir(self.data_dir) if isfile(join(self.data_dir, f))]
        for _i in range(len(files)):
            files[_i] = self.data_dir + "/" + files[_i]

        # print(files)
        for i in self.nb_packets_per_flow:
            self.__generate_pickle_for_n_packets(i, files)

    def __generate_pickle_for_n_packets(self, n, files):
        print("__generate_pickle_for_n_packets n =", n)

        for fold in range(self.nb_folds):
            if self._test_data_prepared((n, fold)):
                print("pickle files detected for ", n, "packets")
                return 
        nb_flows = 0
        df_flows = pd.DataFrame()
        self.classes = set()
        for f in files:
            # print("f=", f)
            start_time = time.time()
            df_new = pd.read_csv(f, 
                                 names = [
                                     'packet_id',
                                     'timestamp', 
                                     'iat',                                                         
                                     'source',
                                     'sport',
                                     'dest', 
                                     'dport',
                                     'protocol', 
                                     'length',
                                     'flow_id'
                                 ],
                                 dtype = {
                                     'flow_id': 'Int32',
                                     'timestamp': np.float64, 
                                     'iat': np.float64,                                                         
                                     'source':str,
                                     'sport': 'Int32',
                                     'dest': str, 
                                     'dport': 'Int32',
                                     'protocol': 'Int32',
                                     'length': 'Int64',
                                     'flow_id': 'Int64'
                                 },
                                 header = 0
                                 )   
            print(n, f, df_new.shape)
            
            # drop DNS traffic
            df_new = df_new.drop(df_new[df_new['sport'] == 53].index)
            df_new = df_new.drop(df_new[df_new['dport'] == 53].index)
            
            found = False
            for k, v in filename_patterns.items():
                if k in f:
                    df_new['class'] = v
                    self.classes.add(v)
                    found = True
                    break
            if found == False:
                print("Type for file", f, "not found")
                sys.exit(1)
            
            # extract flow and add statistical features
            for flow_id in df_new['flow_id'].unique():                    
                nb_flows += 1
                df_new = df_new.sort_values(by = ['packet_id'])
                _df_new = df_new[df_new['flow_id'] == flow_id].head(n = n)
                d = _df_new.head(n = 1)
                d['nb_packets'] = len(_df_new) #df_new[df_new['flow_id'] == flow_id])
                c = d['class'].tolist()
                dport = d.dport.tolist()
                sport = d.sport.tolist()
                #print(d)
                _df = _df_new['iat']
                d['min_iat'] = 0
                d['min_iat'] = np.min(_df_new[_df_new['iat'] > 0]['iat'])
                if len(d[d['iat'] < 0]) > 0:
                    print(_df_new, "has negative iat")
                    continue
                if len(d[d['iat'] > 120]) > 0:
                    print(_df_new, "has iat > 120")
                    continue
                d['max_iat'] = np.max(_df)
                d['sum_iat'] = np.sum(_df)
                d['mean_iat'] = np.mean(_df)
                d['median_iat'] = np.median(_df)
                d['std_iat'] = np.std(_df)
                d['1stQ_iat'] = np.quantile(_df, 0.25)
                d['3rdQ_iat'] = np.quantile(_df, 0.75)
                _a = list(_df)
                d['skew_iat'] = skew(_a)
                d['kurt_iat'] = kurtosis(_a)
                # d['skew_iat'] = skew(np.array(df_new.loc[df_new['flow_id'] == flow_id, 'iat']))
                # d['kurt_iat'] = kurtosis(np.array(df_new.loc[df_new['flow_id'] == flow_id, 'iat']))
                
                _df = _df_new['length']
                d['min_length'] = np.min(_df)
                d['max_length'] = np.max(_df)
                d['sum_length'] = np.sum(_df)
                d['median_length'] = np.median(_df)
                d['mean_length'] = np.mean(_df)
                d['std_length'] = np.std(_df)
                d['1stQ_length'] = np.quantile(_df, 0.25)
                d['3rdQ_length'] = np.quantile(_df, 0.75)
                _a = list(_df)
                d['skew_length'] = skew(_a)
                # d['skew_length'] = skew(np.array(df_new.loc[df_new['flow_id'] == flow_id, 'length']))
                d['kurt_length'] = kurtosis(_a)
                # d['kurt_length'] = kurtosis(np.array(df_new.loc[df_new['flow_id'] == flow_id, 'length']))
                
                d['src'] = f
                df_flows = pd.concat([d, df_flows])

            print(f, "processed in ", time.time() - start_time, "seconds.")            
            
            # uncomment following line to stop after the first file during debug
            # break
                
        print("%d flows processed" % nb_flows)            
        # Finish processing the data, create the train/tests split and save as pickle files
        df_flows = df_flows.fillna(0)
        
        self.classes = list(self.classes)
        self._hotencode_class(df_flows)
        
        filename = self.filename_prefix + "_" + str(n) + ".pickle"
        self._generate_data_folds(df_flows, filename)

    ########################################
    # Data Analysis
    ########################################        
    # def __show_actual_and_predicted(self, X, y, y_pred, _class):
    #     print(self.classes)
    #     for _i in itertools.product(NB_PACKETS, self.filenames):
    #         i = (_i[0], _i[1], 0)
    #         print(i)
    #         df = X[i].copy()
    #         df['type'] = y[i]
    #         df['type_pred'] = y_pred[i]
    #         print(df.columns)
    #         a4_dims = (23.4, 16.54)
    #         fig, ax = plt.subplots(figsize = a4_dims)
    #         sns.lmplot(
    #             x = 'sum_iat', 
    #             y = 'sum_length', 
    #             data = df[df['type'] == _class],
    #             hue = 'type', 
    #             fit_reg = False,
    #             height = 4, aspect = 5,
    #             # color = 'green',
    #             # scatter_kws = {'alpha': 0.3},
    #             # ax = ax,
    #             legend = False,
    #             palette = 'viridis'
    #         )
    #         #ax.set(xlabel='time_delta', ylabel='packet_size')
    #         ax.set(xlabel = 'duration', ylabel = 'sum_packet_size')
    #         plt.legend(title = 'Class', labels =self.classes)
    #         plt.savefig(self.filename_prefix + "_" + self.classes[_class] + "_"+ str(i[0]) + "_" + i[1] + ".png", format = 'png')    
    #         fig, ax2 = plt.subplots(figsize = a4_dims)
    #         sns.lmplot(
    #             x = 'sum_iat', 
    #             y = 'sum_length', 
    #             data = df[df['type_pred'] == _class],
    #             hue = 'type', 
    #             fit_reg = False,
    #             height = 4, aspect = 5,
    #             # color = 'orange',
    #             # scatter_kws = {'alpha': 0.3},
    #             legend = False,
    #             palette = 'viridis',
    #             # ax = ax2
    #         )
    #         ax2.set(xlabel = 'duration', ylabel = 'sum_packet_size')
    #         plt.legend(title = 'Class', labels =self.classes)
    #         plt.savefig(self.filename_prefix + "_" + self.classes[_class] + "_pred_"+ str(i[0]) + "_" + i[1]+".png", format = 'png')
            
    # ########################################
    # # Akem's methods
    # ########################################
    # # Feature Importance
    # """
    # Function to Fit model based on optimal values of depth and number of estimators and use it
    # to compute feature importance for all the features.
    # """
    # def get_feature_importance(depth, n_tree, max_leaf, X_train, y_train):
    #     from sklearn.ensemble import RandomForestClassifier
        
    #     # rf_opt = RandomForestClassifier(max_depth = depth, n_estimators = n_tree, random_state=42, bootstrap=False)
    #     rf_opt = RandomForestClassifier(max_depth = depth, n_estimators = n_tree, max_leaf_nodes=max_leaf, random_state=42, bootstrap=False)
    #     rf_opt.fit(X_train, y_train)
    #     feature_importance = pd.DataFrame(rf_opt.feature_importances_)
    #     feature_importance.index = X_train.columns
    #     feature_importance = feature_importance.sort_values(by=list(feature_importance.columns),axis=0,ascending=False)
        
    #     return feature_importance


    # """
    # Function to Fit model based on optimal values of depth and number of estimators and feature importance
    # to find the fewest possible features to exceed the previously attained score with all selected features
    # """
    # def get_fewest_features(depth, n_tree, max_leaf, importance):    
    #     sorted_feature_names = importance.index
    #     # print('sorted_feature_names: ', sorted_feature_names)
    #     features = []
    #     for f in range(1,len(sorted_feature_names)+1):
    #         features.append(sorted_feature_names[0:f])
    #         # print('features:', features)
    #     return features


    # def get_result_scores(classes, cl_report):
    #     precision=[]
    #     recall=[]
    #     f1_score=[]
    #     supports=[]
    #     for a_class in classes:
    #         precision.append(cl_report[a_class]['precision'])
    #         recall.append(cl_report[a_class]['recall'])
    #         f1_score.append(cl_report[a_class]['f1-score'])
    #         supports.append(cl_report[a_class]['support'])
    #     return precision, recall, f1_score, supports


    # def get_scores(classes, depth, n_tree, feats, max_leaf, X_train, y_train, X_test, y_test):
    #     from sklearn.ensemble import RandomForestClassifier
    #     model = RandomForestClassifier(max_depth=depth, n_estimators = n_tree, max_leaf_nodes=max_leaf, n_jobs=4,
    #                                    random_state=42, bootstrap=False)                              

    #     model.fit(X_train[feats], y_train)
    #     y_pred = model.predict(X_test[feats])
        
    #     class_report = classification_report(y_test, y_pred, target_names=classes, output_dict = True)
        
    #     accurac = model.score(X_test[feats], y_test)
    #     macro_score = class_report['macro avg']['f1-score']
    #     weighted_score = class_report['weighted avg']['f1-score']

    #     return model, class_report, macro_score, weighted_score, y_pred, accurac


    # def get_x_y(Dataset, classes, feats):
    #     Dataset = Dataset[Dataset["Label"].isin(classes)]    
    #     X = Dataset[feats]
    #     y = Dataset['Label'].replace(classes, range(len(classes)))
    #     #     y = Dataset.columns[-1].replace(classes, range(len(classes)))
        
    #     return X, y

    # def analyze_models(classes, model_type, depths, n_trees, X_train, y_train, X_test, y_test, max_leaf, filename_out):
        
    #     with open(filename_out, "w") as res_file:
    #         print('depth;tree;n_feat;Macro_F1;Weighted_F1;Accuracy;feats;c_report', file=res_file)
    #         if model_type == 'RF':
    #             # FOR EACH (depth, n_tree, feat)
    #             for depth in depths:
    #                 for n_tree in n_trees:
    #                     # get feature orders to use
    #                     importance = get_feature_importance(depth, n_tree, max_leaf, X_train, y_train)

    #                     m_feats = get_fewest_features(depth, n_tree, max_leaf, importance) 
    #                     for feats in m_feats:
    #                         # Get the scores with the given (depth, n_tree, feat)
    #                         model, c_report, macro_f1, weight_f1, y_pred, accuracs = get_scores(classes, depth, n_tree, feats, max_leaf, X_train, y_train, X_test, y_test)
                            
    #                         print(str(depth)+';'+str(n_tree)+';'+str(len(feats))+';'+str(macro_f1)+';'+str(weight_f1)+';'+str(accuracs)+';'+str(list(feats))+';'+str(c_report), file=res_file)
    #     print("Analysis Complete. Check output file.")
    #     return []

    # # N = number of packets in flows, feats = array of feature names to use, feat_name = string to add to output file name
    # def analyze_models_for_npkts(self, N, feats, feat_name):
    #     i = (N, self.filenames[0], 0)
    #     print("Number of packets per flow: ", N)
        
    #     X_trains, y_trains = X_train[i][feats], y_train[i]
    #     X_tests,  y_tests  = X_test[i][feats], y_test[i]
        
    #     results_file = "Models_" + feat_name + "_" + str(N) + "_pkts_.csv"
    #     analyze_models(self.classes, "RF", range(7, 20, 1), range(1, 8, 2), X_trains, y_trains, X_tests, y_tests, 500, results_file)
        
    #     results = pd.read_csv(results_file, sep=';')
    #     results = results.sort_values(by=['Weighted_F1','Macro_F1'],ascending=False)
    #     print(results.head(10))
    #     print("******")
    #     print(results.head(1)['c_report'].values)

    ########################################
    # GBoost
    ########################################
    def GBoost_predict(self, feats):
        print("GBoost_predict")
        from sklearn.ensemble import GradientBoostingClassifier
        gb_model = {}
        
        for i in EncryptedTrafficClassifierIterator(self.flow_ids):
            gb_model[i] = GradientBoostingClassifier(n_estimators=100, learning_rate=1.0, max_depth=1, random_state = 42)

        for i in EncryptedTrafficClassifierIterator(self.flow_ids):
            print("==",i,"==")
            try:
                gb_model[i].fit(X_train[i][feats], y_train[i])
            except ValueError as e:
                print(e)
                pass
        
        gb_y_train_predicted = {}
        gb_y_test_predicted = {}
        gb_train_score = {}
        gb_test_score = {}
        for i in EncryptedTrafficClassifierIterator(self.flow_ids):
            print("==",i,"==")
            gb_y_train_predicted[i] = gb_model[i].predict(X_train[i][feats])
            gb_y_test_predicted[i] = gb_model[i].predict(X_test[i][feats])
            gb_train_score[i] = gb_model[i].score(X_train[i][feats], y_train[i])
            gb_test_score[i] = gb_model[i].score(X_test[i][feats], y_test[i])

        self._get_scores_from_models(gb_model, y_test, gb_y_test_predicted, feats)

        gb_cm_dict = {}
        for i in EncryptedTrafficClassifierIterator(self.flow_ids):
            print("==",i,"==")
            gb_cm_dict[i] = confusion_matrix(y_test[i], gb_y_test_predicted[i].astype(int))
            print(gb_cm_dict[i])

        for i in EncryptedTrafficClassifierIterator(self.flow_ids):
            pkt, _ = i
            classification_results.loc[classification_results['nb_packets'] == pkt, 'gb_train_score'] = gb_train_score[i]
            classification_results.loc[classification_results['nb_packets'] == pkt, 'gb_test_score'] = gb_test_score[i]
        
        return gb_model, gb_y_train_predicted, gb_y_test_predicted


########################################
# Entry point
########################################
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='netflow_quic_traffic_classifier',
        description='Classify packets or flows from NetFlow QUIC dataset',
        epilog=''
    )
    parser.add_argument('-p', '--nb_packets', action = 'append', type = int, required = True) #, default = [4, 8])
    parser.add_argument('-c', '--classifier', action = 'append', type = str) #, default = ['rf'])
    parser.add_argument('-f', '--nb_folds', action = 'store', default = 12, type = int)
    parser.add_argument('-v', '--visualization', action = 'store_true', required = False, default = False)
    parser.add_argument('-r', '--report', action = 'store_true', required = False, default = False)
    parser.add_argument('-F', '--force_rf_classification', action = 'store_true', required = False, default = False)
    args = parser.parse_args(sys.argv[1:])

    VISUALIZATION_ENABLED = False
    if args.visualization == True:
        VISUALIZATION_ENABLED = True

    RF_ENABLED = False
    GB_ENABLED = False
    XG_ENABLED = False
    for c in args.classifier:
        c = c.lower()
        if c == "rf":
            RF_ENABLED = True
        elif c == "gb":
            GB_ENABLED = True
        elif c == "xg":
            XG_ENABLED = True
        else:
            print("Unknown classifier", c)
            
    classifier = NetFlowQUICClassifier(
        nb_folds = args.nb_folds,
        nb_packets_per_flow = args.nb_packets
    )

    if args.force_rf_classification == True:
        classifier.force_rf_classification = True

    classifier.all_classes = [
        "youtube",
        "Google_Play_Music",
        "GoogleHangout_VoIP",
        "GoogleHangout_Chat",
        "FileTransfer",
    ]
    
    non_needed_features = [
        'flow_id', 
        'class', 
        'source', 
        'dest', 
        'sport',
        'dport', 
        'protocol', 
        'timestamp', 
        # 'nb_packets',
        'src',
        'iat',
        'direction',
        'length',
        'packet_id'
    ]

    all_features_flows = [
        'min_iat',
        'max_iat',
        'sum_iat',
        'mean_iat',
        'median_iat',
        'std_iat',
        '1stQ_iat',
        '3rdQ_iat', 
        'skew_iat',
        'kurt_iat',
        'min_length',
        'max_length',
        'sum_length',
        'median_length',
        'mean_length', 
        'std_length',
        '1stQ_length',
        '3rdQ_length',
        'skew_length',
        'kurt_length',
        'nb_packets',
        # 'sport',
        # 'dport',
        # 'protocol',
        # 'direction'
    ]
    # best_features = [
    #     'max_iat',
    #     'sum_iat',
    #     'mean_iat',
    #     'median_iat',
    #     'std_iat',
    #     '1stQ_iat',
    #     '3rdQ_iat', 
    #     'skew_iat',
    #     'kurt_iat',
    #     'min_length',
    #     'max_length',
    #     'sum_length',
    #     'median_length',
    #     'mean_length', 
    #     'std_length',
    #     '1stQ_length',
    #     '3rdQ_length',
    #     'skew_length',
    #     'kurt_length'
    # ]
    best_features = ['3rdQ_iat', 'std_iat', 'std_length', 'skew_iat', 'max_iat', 'sum_iat', 'mean_length', '1stQ_length', 'max_length', 'mean_iat', 'min_length', 'sum_length', 'median_length', '1stQ_iat', 'median_iat', '3rdQ_length', 'kurt_iat', 'kurt_length', 'nb_packets']
    online_features=[
        'sum_iat',
        'sum_length',
        'max_length',
        'mean_iat',
        'max_iat',
        'mean_length',
        'min_length',
        'min_iat'
    ]
    feats_flows = all_features_flows
    
    # Preprocessing
    if not classifier.data_prepared():
        classifier.data_preparation()
        classifier.load_flows()
    else:
        classifier.load_flows()
        #_c = classifier.y_train_flows[(classifier.nb_packets_per_flow[0], 0)].unique()
        classifier.classes = [-1 for _ in classifier.all_classes]
        _Xy = classifier.X_train_flows[(classifier.nb_packets_per_flow[0], 0)].copy()
        _Xy['y'] = classifier.y_train_flows[(classifier.nb_packets_per_flow[0], 0)]
        for index, row in _Xy.iterrows():
            for _i in range(len(classifier.all_classes)):
                if classifier.all_classes[_i] in row['src']:
                    classifier.classes[row['y']] = classifier.all_classes[_i]
                    break
                    #classifier.classes[i] .append(classifier.all_classes[i])
            if -1 not in classifier.classes:
                break
        print("classes =",classifier.classes)

        #classifier.classes = []
        #for i in _c:
        #    classifier.classes.append(classifier.all_classes[i])
        
    classifier.cleanup_data(classifier.X_train_flows,
                            classifier.y_train_flows,
                            classifier.X_test_flows,
                            classifier.y_test_flows,
                            classifier.flow_ids,
                            non_needed_features)

    # scaling during processing make results worse !
    # classifier.X_train_flows_fitted, classifier.X_test_flows_fitted = classifier.preprocessing(
    #     classifier.X_train_flows,
    #     classifier.y_train_flows,
    #     classifier.X_test_flows,
    #     classifier.y_test_flows,
    #     classifier.flow_ids,
    #     feats_flows
    # )
    classifier.X_train_flows_fitted = classifier.X_train_flows
    classifier.X_test_flows_fitted = classifier.X_test_flows
    # for i in EncryptedTrafficClassifierIterator(classifier.flow_ids):
    #     # print(classifier.X_train_flows[i].columns)
    #     # print(classifier.X_train_flows[i].index)
    #     # print(classifier.y_train_flows[i].index)
    #     classifier.X_train_flows[i] = classifier.X_train_flows[i][classifier.X_train_flows[i]['sum_iat'] < 120]
    #     classifier.y_train_flows[i] = classifier.y_train_flows[i][classifier.X_train_flows[i].index]
    #     classifier.X_test_flows[i] = classifier.X_test_flows[i][classifier.X_test_flows[i]['sum_iat'] < 120]
    #     classifier.y_test_flows[i] = classifier.y_test_flows[i][classifier.X_test_flows[i].index]
    
    # __correlation()
    # analyze_models_for_npkts(10, all_features, "all_feats")
    if args.report == True:
        __class_names = { 
            "youtube": "YouTube",
            "Google_Play_Music": "Music",
            "GoogleHangout_VoIP": "VoIP",
            "GoogleHangout_Chat": "Chat",
            "FileTransfer": "FileTransfer",
            }
        for _c in range(len(classifier.classes)):
            classifier.classes[_c] = __class_names[classifier.classes[_c]]
        classifier._viz(distribution = 0, class_distribution = -1, nb_packets = -1, min_iat = -1, max_iat = -1)
        for n in classifier.nb_packets_per_flow:
            if n == 4:
                classifier._viz(distribution = -1, class_distribution = 10, nb_packets = 0, min_iat = -1, max_iat = -1)
            elif n == 8:
                classifier._viz(distribution = -1, class_distribution = 10, nb_packets = 0, min_iat = -1, max_iat = -1)
            elif n == 600000:
                classifier._viz(distribution = -1, class_distribution = 11, nb_packets = 1, min_iat = 1, max_iat = -1)
        sys.exit(1)
    if VISUALIZATION_ENABLED:
        # classifier.classes= ["Chat", "Music", "YouTube", "VoIP", "FileTransfer"]
        # classifier._viz(distribution = 0, class_distribution = 10, nb_packets = -1, min_iat = 1, max_iat = -1)
        # sys.exit(1)
        
        # f = classifier.filename_prefix + '_datasetflows_distribution.pickle'
        # if isfile(classifier.processed_data_output_dir + f):
        #     print("Loading dataset from pickle file", f)
        #     _df = classifier._load_pickle(f)
        # else:
        #     print("Creating dataset")
        #     _df = classifier._get_flows_with_all_packets()
        #     classifier._pickle_dump(_df, f)
        #     print("Dataset saved in file", f)
        # classifier._class_distribution(_df, classifier.filename_prefix + '_flows_distribution')
        # classifier._nb_packets_distribution(_df, classifier.filename_prefix + "_flows_nb_packets_distribution" )
        # classifier._distribution(_df, classifier.filename_prefix + "_flows_class_split" )
        
        __class_names = { 
            "youtube": "YouTube",
            "Google_Play_Music": "Music",
            "GoogleHangout_VoIP": "VoIP",
            "GoogleHangout_Chat": "Chat",
            "FileTransfer": "FileTransfer",
            }
        for _c in range(len(classifier.classes)):
            classifier.classes[_c] = __class_names[classifier.classes[_c]]
        pkt = classifier.nb_packets_per_flow[0]
        fold = 0
        _i = pkt, fold
        _df1 = classifier.X_train_flows[_i].copy()
        _df1['type'] = classifier.y_train_flows[_i].values
        _df2 = classifier.X_test_flows[_i].copy()
        _df2['type'] = classifier.y_test_flows[_i].values
        _df = pd.concat([_df1, _df2])
        _df.reset_index()
        # _df = _df[_df['sum_iat'] < 120]
        # _df.to_csv("netflow_datasets_pkts_"+str(pkt)+".csv", index = False)
        # sys.exit(1)
        print(_df.shape)
        classifier._distribution(_df, classifier.filename_prefix + "_flows_class_split_" + str(pkt) + '_pkt')
        sys.exit(1)
        # classifier._class_distribution(_df, classifier.filename_prefix + '_flows_distribution_' + str(pkt) + '_pkt')
        # classifier._nb_packets_distribution(_df, classifier.filename_prefix + "_flows_nb_packets_distribution_" + str(pkt) + '_pkt')
        # classifier._min_iat_distribution(_df, classifier.filename_prefix + "_flows_min_iat_distribution_" + str(pkt) + '_pkt')

    if RF_ENABLED:
        print("==== RandomForest =====")
        __class_names = { 
            "youtube": "YouTube",
            "Google_Play_Music": "Music",
            "GoogleHangout_VoIP": "VoIP",
            "GoogleHangout_Chat": "Chat",
            "FileTransfer": "FileTransfer",
            }
        for _c in range(len(classifier.classes)):
            classifier.classes[_c] = __class_names[classifier.classes[_c]]
        
        rf_regr_flows, rf_y_train_flows_predicted, rf_y_test_flows_predicted = classifier.RF_predict(
                classifier.X_train_flows_fitted,
                classifier.y_train_flows,
                classifier.X_test_flows_fitted,
                classifier.y_test_flows
        )
                
        # __show_actual_and_predicted(X_test, y_test, rf_y_test_predicted, 1)
        rf_cm_dict_flows, output = classifier.confusion_matrix(rf_regr_flows,
                                                               classifier.y_test_flows,
                                                               rf_y_test_flows_predicted,
                                                               classifier.flow_ids,
                                                               "rf"
                                                               )
        print(output)
        rf_f1_scores_flows, output = classifier.get_F1_score(rf_cm_dict_flows,
                                                             classifier.y_test_flows,
                                                             rf_y_test_flows_predicted,
                                                             classifier.flow_ids,
                                                             "rf_flows")
        print(output)
        avg_scores, output = classifier.avg_f1_scores(rf_f1_scores_flows, classifier.flow_ids) #_without_folds)
        print(output)

    if GB_ENABLED:
        print("==== GradientBoosting =====")
        gb_regr, gb_y_train_predicted, gb_y_test_predicted  = classifier.GBoost_predict(feats_flows, classification_results)
        gb_cm_dict = classifier.confusion_matrix(gb_regr, classifier.y_test_flows, gb_y_test_predicted, classifier.flow_ids, "gb")
        gb_f1_scores = classifier.get_F1_score(gb_cm_dict,  y_test, gb_y_test_predicted, "gb", False)
        classifier.avg_f1_scores(gb_f1_scores_flows, classifier.flow_ids_without_folds)
        # classifier.avg_f1_scores(gb_f1_scores)

    if XG_ENABLED:
        print("==== XGBoost =====")
        xg_regr, xg_y_train_predicted, xg_y_test_flows_predicted = classifier.XGBoost_predict(
            classifier.X_train_flows_fitted,
            classifier.y_train_flows,
            classifier.X_test_flows_fitted,
            classifier.y_test_flows
        )
        
        xg_cm_dict_flows, output = classifier.confusion_matrix(xg_regr,
                                                               classifier.y_test_flows,
                                                               xg_y_test_flows_predicted,
                                                               classifier.flow_ids,
                                                               "xg"
                                                               )
        print(output)
            
        xg_f1_scores_flows, output = classifier.get_F1_score(
            xg_cm_dict_flows,
            classifier.y_test_flows,
            xg_y_test_flows_predicted,
            classifier.flow_ids,
            "xg_flows")
        print(output)
        # xg_cm_dict, classifier.y_test_flows, xg_y_test_predicted, "xg", False)
        avg_scores, output = classifier.avg_f1_scores(xg_f1_scores_flows, classifier.flow_ids)
        print(output)
        # print(xg_f1_scores)

    print(classifier.classification_results)
    if RF_ENABLED or GB_ENABLED or XG_ENABLED:
        classifier.save_results()