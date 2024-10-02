# -*- coding: utf-8 -*-
'''
Interpretable Machine-Learning - Modelling (MDL)
v751
@author: Dr. David Steyrl david.steyrl@univie.ac.at
'''

import math
import numpy as np
import os
import pandas as pd
import pickle
import shutil
import warnings
from lightgbm import LGBMClassifier
from lightgbm import LGBMRegressor
from scipy.stats import loguniform
from scipy.stats import randint
from scipy.stats import uniform
from shap.explainers import Tree as TreeExplainer
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.compose import TransformedTargetRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error
from sklearn.metrics import balanced_accuracy_score
from sklearn.metrics import r2_score
from sklearn.model_selection import RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import TargetEncoder
from sklearn.utils import shuffle
from sklearn_repeated_group_k_fold import RepeatedGroupKFold
from time import time


def create_dir(path):
    '''
    Create specified directory if not existing.

    Parameters
    ----------
    path : string
        Path to to check to be created.

    Returns
    -------
    None.
    '''

    # Create dir of not existing ----------------------------------------------
    # Check if dir exists
    if not os.path.isdir(path):
        # Create dir
        os.mkdir(path)

    # Return None -------------------------------------------------------------
    return


def prepare(task):
    '''
    Prepare analysis pipeline, prepare seach_space.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.

    Returns
    -------
    pipe : scikit-learn compatible analysis pipeline
        Prepared pipe object.
    space : dict
        Space that should be searched for optimale parameters.
    '''

    # Make preprocessing pipe -------------------------------------------------
    # Instatiate target-encoder
    te = TargetEncoder(
        categories=task['te_categories'],
        target_type='continuous',
        smooth='auto',
        cv=5,
        shuffle=True,
        random_state=None)
    # Get categorical predictors for target-encoder
    coltrans = ColumnTransformer(
        [('con_pred', 'passthrough', task['X_CON_NAMES']),
         ('bin_pred', 'passthrough', task['X_CAT_BIN_NAMES']),
         ('mult_pred', te, task['X_CAT_MULT_NAMES']),
         ],
        remainder='drop',
        sparse_threshold=0,
        n_jobs=1,
        transformer_weights=None,
        verbose=False,
        verbose_feature_names_out=False)
    # Pipeline
    pre_pipe = Pipeline(
        [('coltrans', coltrans), ('std_scaler', StandardScaler())],
        memory=None,
        verbose=False)

    # Make predictor ----------------------------------------------------------
    # Regression
    if task['OBJECTIVE'] == 'regression':
        # Estimator
        estimator = LGBMRegressor(
            boosting_type='gbdt',
            num_leaves=100,
            max_depth=-1,
            learning_rate=0.01,
            n_estimators=1000,
            subsample_for_bin=100000,
            objective=task['OBJECTIVE'],
            min_split_gain=0.0,
            min_child_weight=0.001,
            min_child_samples=2,
            subsample=1.0,
            subsample_freq=0,
            colsample_bytree=1.0,
            reg_alpha=0.0,
            reg_lambda=0.0,
            random_state=None,
            n_jobs=1,
            importance_type='gain',
            **{'data_random_seed': None,
               'data_sample_strategy': 'bagging',
               'extra_seed': None,
               'feature_fraction_seed': None,
               'feature_pre_filter': False,
               'force_col_wise': True,
               'max_bin': 100,
               'min_data_in_bin': 1,
               # 'use_quantized_grad': True,
               'verbosity': -1,
               })
        # Search space
        space = {
            'estimator__regressor__colsample_bytree': uniform(0.1, 0.9),
            'estimator__regressor__extra_trees': [True, False],
            'estimator__regressor__path_smooth': loguniform(1, 1000),
            }
        # Add scaler to the estimator
        estimator = TransformedTargetRegressor(
            regressor=estimator,
            transformer=StandardScaler(),
            func=None,
            inverse_func=None,
            check_inverse=True)
    # Classification
    elif task['OBJECTIVE'] == 'binary' or task['OBJECTIVE'] == 'multiclass':
        # Estimator
        estimator = LGBMClassifier(
            boosting_type='gbdt',
            num_leaves=100,
            max_depth=-1,
            learning_rate=0.01,
            n_estimators=1000,
            subsample_for_bin=100000,
            objective=task['OBJECTIVE'],
            class_weight='balanced',
            min_split_gain=0.0,
            min_child_weight=0.001,
            min_child_samples=2,
            subsample=1.0,
            subsample_freq=0,
            colsample_bytree=1.0,
            reg_alpha=0.0,
            reg_lambda=0.0,
            random_state=None,
            n_jobs=1,
            importance_type='gain',
            **{'data_random_seed': None,
               'data_sample_strategy': 'bagging',
               'extra_seed': None,
               'feature_fraction_seed': None,
               'feature_pre_filter': False,
               'force_col_wise': True,
               'max_bin': 100,
               'min_data_in_bin': 1,
               # 'use_quantized_grad': True,
               'verbosity': -1,
               })
        # Search space
        space = {
            'estimator__colsample_bytree': uniform(0.1, 0.9),
            'estimator__extra_trees': [True, False],
            'estimator__path_smooth': loguniform(1, 1000),
            }
    # Other
    else:
        # Raise error
        raise ValueError('OBJECTIVE not found.')

    # Make full pipeline ------------------------------------------------------
    # Analyis pipeline
    pipe = Pipeline(
        [('preprocessing', pre_pipe),
         ('estimator', estimator)],
        memory=None,
        verbose=False).set_output(transform='pandas')

    # Return pipe and space ---------------------------------------------------
    return pipe, space


def split_data(df, i_trn, i_tst):
    '''
    Split dataframe in training and testing dataframes.

    Parameters
    ----------
    df : dataframe
        Dataframe holding the data to split.
    i_trn : numpy array
        Array with indices of training data.
    i_tst : numpy array
        Array with indices of testing data.

    Returns
    -------
    df_trn : dataframe
        Dataframe holding the training data.
    df_tst : dataframe
         Dataframe holding the testing data.
    '''

    # Split dataframe via index -----------------------------------------------
    # Dataframe is not empty
    if not df.empty:
        # Make split
        df_trn = df.iloc[i_trn].reset_index(drop=True)
        # Make split
        df_tst = df.iloc[i_tst].reset_index(drop=True)
    # Dataframe is empty
    else:
        # Make empty dataframes
        df_trn, df_tst = pd.DataFrame(), pd.DataFrame()

    # Return train test dataframes --------------------------------------------
    return df_trn, df_tst


def print_tune_summary(task, i_cv, n_splits, hp_params, hp_score):
    '''
    Print best paramters and related score to console.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    i_cv : int
        Current cv repetition.
    n_splits : int
        Number of splits in inner cv
    hp_params : dictionary
        Best hyper params found.
    hp_score : dictionary
        Score for best hyper params found.

    Returns
    -------
    None.
    '''

    # Print analysis name
    print('Analysis: '+task['ANALYSIS_NAME'])
    # Print data set
    print('Dataset: '+task['PATH_TO_DATA'])
    # Cross-validation --------------------------------------------------------
    if task['TYPE'] == 'CV':
        # Regression
        if task['OBJECTIVE'] == 'regression':
            # Print general information
            print(
                str(task['i_y'])+'.'+str(i_cv)+' | ' +
                'n rep outer cv: '+str(task['N_REP_OUTER_CV'])+' | ' +
                'n rep inner cv: '+str(n_splits)+' | ' +
                'best neg MSE: '+str(np.round(hp_score, decimals=4)))
        # Classification
        elif (task['OBJECTIVE'] == 'binary' or
              task['OBJECTIVE'] == 'multiclass'):
            # Print general information
            print(
                str(task['i_y'])+'.'+str(i_cv)+' | ' +
                'n rep outer cv: '+str(task['N_REP_OUTER_CV'])+' | ' +
                'n rep inner cv: '+str(n_splits)+' | ' +
                'acc: '+str(np.round(hp_score, decimals=4)))
        # Other
        else:
            # Raise error
            raise ValueError('OBJECTIVE not found.')
    # Train-Test split --------------------------------------------------------
    elif task['TYPE'] == 'TT':
        # Regression
        if task['OBJECTIVE'] == 'regression':
            # Print general information
            print(
                str(task['i_y'])+'.'+str(i_cv)+' | ' +
                'n rep inner cv: '+str(n_splits)+' | ' +
                'best neg MSE: '+str(np.round(hp_score, decimals=4)))
        # Classification
        elif (task['OBJECTIVE'] == 'binary' or
              task['OBJECTIVE'] == 'multiclass'):
            # Print general information
            print(
                str(task['i_y'])+'.'+str(i_cv)+' | ' +
                'n rep inner cv: '+str(n_splits)+' | ' +
                'acc: '+str(np.round(hp_score, decimals=4)))
        # Other
        else:
            # Raise error
            raise ValueError('OBJECTIVE not found.')
    # Other -------------------------------------------------------------------
    else:
        # Raise error
        raise ValueError('TYPE not found.')
    # Print best hyperparameter and related score for regression task
    print(str(hp_params))

    # Return None -------------------------------------------------------------
    return


def tune_pipe(task, i_cv, pipe, space, g_trn, x_trn, y_trn):
    '''
    Inner loop of the nested cross-validation. Runs a search for optimal
    hyperparameter (random search).
    Ref: Hastie T, Tibshirani R, Friedman JH. The elements of statistical
    learning: data mining, inference, and prediction. 2nd ed. New York,
    NY: Springer; 2009.
    Ref: Cawley GC, Talbot NLC. On Over-ﬁtting in Model Selection and
    Subsequent Selection Bias in Performance Evaluation. 2010;(11):2079–107.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    i_cv : int
        Current iteration of outer cross-validation.
    pipe : pipeline object
        Analysis pipeline.
    space : dict
        Space that should be searched for optimale parameters.
    g_trn : ndarray (n_samples)
        Group data.
    x_trn : ndarray (n_features x n_samples)
        Predictor train data.
    y_trn : ndarray (n_samples)
        Target train data.

    Returns
    -------
    pipe : pipeline object
        Fitted pipeline object with tuned parameters.
    best parameters : dict
        Best hyperparameters of the pipe.
    '''

    # Get scorer --------------------------------------------------------------
    # Regression
    if task['OBJECTIVE'] == 'regression':
        # neg_mean_squared_error
        scorer = 'neg_mean_squared_error'
    # Classification
    elif task['OBJECTIVE'] == 'binary' or task['OBJECTIVE'] == 'multiclass':
        # Weighted accuracy for classification
        scorer = 'balanced_accuracy'
    # Other
    else:
        # Raise error
        raise ValueError('OBJECTIVE not found.')

    # Tune analysis pipeline --------------------------------------------------
    # Choose n_repeats to approx N_SAMPLES_INNER_CV predictions
    n_repeats = math.ceil(task['N_SAMPLES_INNER_CV'] / g_trn.shape[0])
    # Instatiate random parameter search
    search = RandomizedSearchCV(
        pipe,
        space,
        n_iter=task['N_SAMPLES_RS'],
        scoring=scorer,
        n_jobs=task['N_JOBS'],
        refit=True,
        cv=RepeatedGroupKFold(n_splits=5,
                              n_repeats=n_repeats,
                              random_state=None),
        verbose=0,
        pre_dispatch='2*n_jobs',
        random_state=None,
        error_score=0,
        return_train_score=False)
    # Random search for best parameter
    search.fit(x_trn, y_trn.squeeze(), groups=g_trn)
    # Print tune summary
    print_tune_summary(
        task,
        i_cv,
        n_repeats,
        search.best_params_,
        search.best_score_)

    # Return tuned analysis pipe ----------------------------------------------
    return search.best_estimator_, search.best_params_


def score_predictions(task, pipe, x_tst, y_tst, y):
    '''
    Compute scores for predictions based on task.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    pipe : pipeline object
        Analysis pipeline.
    x_tst : ndarray (n_features x n_samples)
        Predictor test data.
    y_tst : ndarray (n_samples)
        Target test data.
    y : ndarray
        All available target data to compute true class weights for scoring.

    Returns
    -------
    scores : dict
        Returns scoring results. MAE, MSE and R² if task is regression.
        ACC and true class weights if task is classification.
    '''

    # Predict -----------------------------------------------------------------
    # Predict test samples
    y_pred = pipe.predict(x_tst)

    # Score results -----------------------------------------------------------
    # Regression
    if task['OBJECTIVE'] == 'regression':
        # Score predictions in terms of mae
        mae = mean_absolute_error(y_tst, y_pred)
        # Score predictions in terms of mse
        mse = mean_squared_error(y_tst, y_pred)
        # Score predictions in terms of R²
        r2 = r2_score(y_tst, y_pred)
        # Results
        scores = {
            'y_true': y_tst.squeeze().to_numpy(),
            'y_pred': y_pred,
            'mae': mae,
            'mse': mse,
            'r2': r2}
    # Classification
    elif task['OBJECTIVE'] == 'binary' or task['OBJECTIVE'] == 'multiclass':
        # Calculate model fit in terms of acc
        acc = balanced_accuracy_score(y_tst, y_pred)
        # Results
        scores = {
            'y_true': y_tst.squeeze().to_numpy(),
            'y_pred': y_pred,
            'acc': acc}
    # Other
    else:
        # Raise error
        raise ValueError('OBJECTIVE not found.')

    # Return scores -----------------------------------------------------------
    return scores


def get_explainations(task, pipe, x_trn, x_tst):
    '''
    Get SHAP (SHapley Additive exPlainations) model explainations.
    Ref: Molnar, Christoph. 'Interpretable machine learning. A Guide for
    Making Black Box Models Explainable', 2019.
    https://christophm.github.io/interpretable-ml-book/.
    Ref: Lundberg, Scott M., and Su-In Lee. “A unified approach to
    interpreting model predictions.” Advances in Neural Information Processing
    Systems. 2017.
    Ref: Lundberg, Scott M., Gabriel G. Erion, and Su-In Lee. “Consistent
    individualized feature attribution for tree ensembles.” arXiv preprint
    arXiv:1802.03888 (2018).
    Ref: Sundararajan, Mukund, and Amir Najmi. “The many Shapley values for
    model explanation.” arXiv preprint arXiv:1908.08474 (2019).
    Ref: Janzing, Dominik, Lenon Minorics, and Patrick Blöbaum. “Feature
    relevance quantification in explainable AI: A causality problem.” arXiv
    preprint arXiv:1910.13413 (2019).
    Ref: Slack, Dylan, et al. “Fooling lime and shap: Adversarial attacks on
    post hoc explanation methods.” Proceedings of the AAAI/ACM Conference on
    AI, Ethics, and Society. 2020.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    pipe : pipeline object
        Fitted pipeline object with tuned parameters.
    x_trn : ndarray (n_features x n_samples)
        Background data.
    x_tst : ndarray (n_features x n_samples)
        Test data for shap computation.

    Returns
    -------
    imp : shap explainer object
        SHAP based predictor importance.
    '''

    # Get SHAP test data ------------------------------------------------------
    # Subsample test data
    x_tst_shap_orig = x_tst.sample(
        n=min(x_tst.shape[0], task['MAX_SAMPLES_SHAP']),
        random_state=3141592,
        ignore_index=True)
    # Transform shap test data
    x_tst_shap = pipe[0].transform(x_tst_shap_orig)

    # Explainer and Explainations ---------------------------------------------
    # Regression
    if task['OBJECTIVE'] == 'regression':
        # Get predictor
        predictor = pipe[1].regressor_
    # Classification
    elif task['OBJECTIVE'] == 'binary' or task['OBJECTIVE'] == 'multiclass':
        # Get predictor
        predictor = pipe[1]
    # Get explainer
    explainer = TreeExplainer(
        predictor,
        data=None,
        model_output='raw',
        feature_perturbation='tree_path_dependent',
        feature_names=None,
        approximate=False)
    # Get explainations with interactions
    if task['SHAP_INTERACTIONS']:
        # Get shap values
        shap_explainations = explainer(
            x_tst_shap,
            interactions=True,
            check_additivity=False)
    # Get explainations without interactions
    elif not task['SHAP_INTERACTIONS']:
        # Get shap values
        shap_explainations = explainer(
            x_tst_shap,
            interactions=False,
            check_additivity=False)
    # Other
    else:
        # Raise error
        raise ValueError('Invalid value for SHAP_INTERACTIONS.')

    # Prepare shap_explainations ----------------------------------------------
    # Replace scaled data in shap explainations with unscaled
    shap_explainations.data = x_tst_shap_orig
    # If regression
    if task['OBJECTIVE'] == 'regression':
        # Rescale shap values from scaled data to original space
        shap_explainations.values = (
            shap_explainations.values*pipe[1].transformer_.scale_[0])
        # Rescale shap base values from scaled data to original space
        shap_explainations.base_values = (
            (shap_explainations.base_values*pipe[1].transformer_.scale_[0]) +
            pipe[1].transformer_.mean_[0])

    # Return shap explainations -----------------------------------------------
    return shap_explainations


def s2p(path_save, variable):
    '''
    Save variable as pickle file at path.

    Parameters
    ----------
    path_save : string
        Path ro save variable.
    variable : string
        Variable to save.

    Returns
    -------
    None.
    '''

    # Save --------------------------------------------------------------------
    # Save variable as pickle file
    with open(path_save, 'wb') as filehandle:
        # store the data as binary data stream
        pickle.dump(variable, filehandle)

    # Return None -------------------------------------------------------------
    return


def print_current_results(task, t_start, scores, scores_sh):
    '''
    Print current results to console.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    t_start : time
        Start time of the current cross-validation loop.
    scores : dict
        Scores dict.
    scores_sh : dict
        Scores with shuffled data dict.

    Returns
    -------
    None.
    '''

    # Print results -----------------------------------------------------------
    # Regression
    if task['OBJECTIVE'] == 'regression':
        # Print current R2
        print(
            'Current CV loop R2: '+str(np.round(
                scores[-1]['r2'], decimals=4)))
        # Print running mean R2
        print(
            'Running mean R2: '+str(np.round(
                np.mean([i['r2'] for i in scores]), decimals=4)))
        # Print running mean shuffle R2
        print(
            'Running shuffle mean R2: '+str(np.round(
                np.mean([i['r2'] for i in scores_sh]), decimals=4)))
        # Print elapsed time
        print(
            'Elapsed time: '+str(np.round(
                time() - t_start, decimals=1)), end='\n\n')
    # Classification
    elif task['OBJECTIVE'] == 'binary' or task['OBJECTIVE'] == 'multiclass':
        # Print current acc
        print(
            'Current CV loop acc: '+str(np.round(
                scores[-1]['acc'], decimals=4)))
        # Print running mean acc
        print(
            'Running mean acc: '+str(np.round(
                np.mean([i['acc'] for i in scores]), decimals=4)))
        # Print running mean shuffle acc
        print(
            'Running shuffle mean acc: '+str(np.round(
                np.mean([i['acc'] for i in scores_sh]), decimals=4)))
        # Print elapsed time
        print(
            'Elapsed time: '+str(np.round(
                time() - t_start, decimals=1)), end='\n\n')
    # Other
    else:
        # Raise error
        raise ValueError('OBJECTIVE not found.')

    # Return None -------------------------------------------------------------
    return


def cross_validation(task, g, x, y):
    '''
    Performe cross-validation analysis. Saves results to pickle file in
    path_to_results directory.
    Ref: Hastie T, Tibshirani R, Friedman JH. The elements of statistical
    learning: data mining, inference, and prediction. 2nd ed. New York,
    NY: Springer; 2009
    Ref: Cawley GC, Talbot NLC. On Over-ﬁtting in Model Selection and
    Subsequent Selection Bias in Performance Evaluation. 2010;(11):2079–107.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    g : dataframe
        Groups dataframe.
    x : dataframe
        Predictors dataframe.
    y : dataframe
        Target dataframe.

    Returns
    -------
    None.
    '''

    # Initialize results lists ------------------------------------------------
    # Initialize best params list
    best_params = []
    # Initialize score list
    scores = []
    # Initialize SHAP based explainations list
    explainations = []
    # Initialize shuffle data score list
    scores_sh = []
    # Initialize shuffle data SHAP based explainations list
    explainations_sh = []
    # Get analysis pipeline and space
    pipe, space = prepare(task)

    # Main cross-validation loop ----------------------------------------------
    # Instatiate main cv splitter with fixed random state for comparison
    cv = RepeatedGroupKFold(
        n_splits=5,
        n_repeats=task['N_REP_OUTER_CV'],
        random_state=3141592)
    # Loop over main (outer) cross validation splits
    for i_cv, (i_trn, i_tst) in enumerate(cv.split(g, groups=g)):
        # Save loop start time
        t_start = time()

        # Split data ----------------------------------------------------------
        # Split groups
        g_trn, g_tst = split_data(g, i_trn, i_tst)
        # Split targets
        y_trn, y_tst = split_data(y, i_trn, i_tst)
        # Split predictors
        x_trn, x_tst = split_data(x, i_trn, i_tst)

        # Tune and fit --------------------------------------------------------
        # Get optimized and fitted pipe
        pipe, params = tune_pipe(task, i_cv, pipe, space, g_trn, x_trn, y_trn)
        # Store best params
        best_params.append(params)

        # Analyze -------------------------------------------------------------
        # Score predictions
        scores.append(score_predictions(task, pipe, x_tst, y_tst, y))
        # SHAP explainations
        explainations.append(get_explainations(task, pipe, x_trn, x_tst))

        # Shuffle data analyze ------------------------------------------------
        # Clone pipe
        pipe_sh = clone(pipe)
        # Refit pipe with shuffled targets
        pipe_sh.fit(x_trn, shuffle(y_trn).squeeze())
        # Score predictions
        scores_sh.append(score_predictions(task, pipe_sh, x_tst, y_tst, y))
        # SHAP explainations
        explainations_sh.append(get_explainations(task, pipe_sh, x_trn, x_tst))

        # Compile and save intermediate results and task ----------------------
        # Create results
        results = {
            'best_params': best_params,
            'scores': scores,
            'explainations': explainations,
            'scores_sh': scores_sh,
            'explainations_sh': explainations_sh
            }
        # Make save path
        save_path = task['path_to_results']+'/'+task['y_name'][0]
        # Save results as pickle file
        s2p(save_path+'_results.pickle', results)
        # Save task as pickle file
        s2p(save_path+'_task.pickle', task)

        # Print current results -----------------------------------------------
        print_current_results(task, t_start, scores, scores_sh)

    # Return None -------------------------------------------------------------
    return


def train_test_split(task, g, x, y):
    '''
    Performe train-test split analysis. Saves results to pickle file in
    path_to_results directory.
    Ref: Hastie T, Tibshirani R, Friedman JH. The elements of statistical
    learning: data mining, inference, and prediction. 2nd ed. New York,
    NY: Springer; 2009
    Ref: Cawley GC, Talbot NLC. On Over-ﬁtting in Model Selection and
    Subsequent Selection Bias in Performance Evaluation. 2010;(11):2079–107.

    Parameters
    ----------
    task : dictionary
        Dictionary holding the task describtion variables.
    g : dataframe
        Groups dataframe.
    x : dataframe
        Predictors dataframe.
    y : dataframe
        Target dataframe.

    Returns
    -------
    None.
    '''

    # Initialize results lists ------------------------------------------------
    # Initialize best params list
    best_params = []
    # Initialize score list
    scores = []
    # Initialize SHAP based explainations list
    explainations = []
    # Initialize shuffle data score list
    scores_sh = []
    # Initialize shuffle data SHAP based explainations list
    explainations_sh = []
    # Get analysis pipeline and space
    pipe, space = prepare(task)
    # Save start time
    t_start = time()

    # Split data --------------------------------------------------------------
    # Get train data index
    i_trn = list(set(g.index).difference(set(task['TEST_SET_IND'])))
    # Get test data index
    i_tst = task['TEST_SET_IND']
    # Splitting groups
    g_trn, g_tst = split_data(g, i_trn, i_tst)
    # Splitting targets
    y_trn, y_tst = split_data(y, i_trn, i_tst)
    # Splitting predictors
    x_trn, x_tst = split_data(x, i_trn, i_tst)

    # Tune and fit ------------------------------------------------------------
    # Get optimized and fitted pipe
    pipe, params = tune_pipe(task, 0, pipe, space, g_trn, x_trn, y_trn)
    # Store best params
    best_params.append(params)

    # Analyze -----------------------------------------------------------------
    # Score predictions
    scores.append(score_predictions(task, pipe, x_tst, y_tst, y))
    # SHAP explainations
    explainations.append(get_explainations(task, pipe, x_trn, x_tst))

    # Shuffle data analyze ----------------------------------------------------
    # Clone pipe
    pipe_sh = clone(pipe)
    # Refit pipe with shuffled targets
    pipe_sh.fit(x_trn, shuffle(y_trn).squeeze())
    # Score predictions
    scores_sh.append(score_predictions(task, pipe_sh, x_tst, y_tst, y))
    # SHAP explainations
    explainations_sh.append(get_explainations(task, pipe_sh, x_trn, x_tst))

    # Compile and save intermediate results and task --------------------------
    # Create results
    results = {
        'best_params': best_params,
        'scores': scores,
        'explainations': explainations,
        'scores_sh': scores_sh,
        'explainations_sh': explainations_sh
        }
    # Make save path
    save_path = task['path_to_results']+'/'+task['y_name'][0]
    # Save results as pickle file
    s2p(save_path+'_results.pickle', results)
    # Save task as pickle file
    s2p(save_path+'_task.pickle', task)

    # Print current results ---------------------------------------------------
    print_current_results(task, t_start, scores, scores_sh)

    # Return None -------------------------------------------------------------
    return


def main():
    '''
    Main function of the machine-learning based data analysis.

    Returns
    -------
    None.
    '''

    ###########################################################################
    # Specify analysis
    ###########################################################################

    # 1. Specify task ---------------------------------------------------------

    # Type of analysis. str (default: CV)
    # Repeated Cross-validation: CV
    # Single Train-Test split: TT
    TYPE = 'CV'
    # Number parallel processing jobs. int (-1=all, -2=all-1)
    N_JOBS = -2
    # CV: Number of outer CV repetitions. int (default: 10)
    N_REP_OUTER_CV = 10
    # CV & TT: Min number of predictions inner CV. int (default: 1000)
    N_SAMPLES_INNER_CV = 1000
    # Number of samples random search. int (default: 100)
    N_SAMPLES_RS = 100
    # Number of samples SHAP. int (default: 100).
    MAX_SAMPLES_SHAP = 100
    # Get SHAP interactions. bool (default: True)
    SHAP_INTERACTIONS = True

    # 2. Specify data ---------------------------------------------------------

    # Personality and creativity data - regression
    # Specifiy an analysis name
    ANALYSIS_NAME = 'PerCrea'
    # Specify path to data. string
    PATH_TO_DATA = 'data/final_data_1line_BS_David_20240201.xlsx'
    # Specify sheet name. string
    SHEET_NAME = 'David_data'
    # Specify task OBJECTIVE. string (regression, binary, multiclass)
    OBJECTIVE = 'regression'
    # Specify grouping for CV split. list of string
    G_NAME = [
        'case'
        ]
    # Specify continous predictor names. list of string or []
    X_CON_NAMES = [
        'HY_score',
        'MOCA',
        'pre-symptomatic-baseline_creativity',
        'symptom-onset_creativity',
        'post-diagnosis_creativity',
        'BIG5_extraversion',
        'BIG5_agreeableness',
        'BIG5_conscientiousness',
        'BIG5_neuroticism',
        'BIG5_openness',
        'positive_schizotypy',
        'negative_schizotypy',
        'disorganized_schizotypy',
        ]
    # Specify binary categorical predictor names. list of string or []
    X_CAT_BIN_NAMES = [
        'personal_reaction_to_living situation_post-diagnosis',
        'external_care-giver_initiated',
        'increased_freetime',
        'post-diagnosis_levodopa',
        'post-diagnosis_DA-agonist',
        'current_levodopa',
        'current_DA-agonist',
       ]
    # Specify multi categorical predictor names. list of string or []
    X_CAT_MULT_NAMES = []
    # Specify target name(s). list of strings or []
    Y_NAMES = [
        'current_creativity',
        ]
    # Rows to skip. list of int or []
    SKIP_ROWS = []
    # Specify index of rows for test set if TT. list of int or []
    TEST_SET_IND = []

    ###########################################################################

    # Add to analysis name ----------------------------------------------------
    # If shap with interactions
    if SHAP_INTERACTIONS:
        # Update string
        ANALYSIS_NAME = ANALYSIS_NAME+'_'+TYPE+'_'+'inter'
    # If shap without interactions
    elif not SHAP_INTERACTIONS:
        # Update string
        ANALYSIS_NAME = ANALYSIS_NAME+'_'+TYPE
    # Other
    else:
        # Raise error
        raise ValueError('SHAP_INTERACTIONS can be True or False only.')

    # Create results directory path -------------------------------------------
    path_to_results = 'res_ml_'+ANALYSIS_NAME

    # Create task variable ----------------------------------------------------
    task = {
        'TYPE': TYPE,
        'N_JOBS': N_JOBS,
        'N_REP_OUTER_CV': N_REP_OUTER_CV,
        'N_SAMPLES_INNER_CV': N_SAMPLES_INNER_CV,
        'N_SAMPLES_RS': N_SAMPLES_RS,
        'MAX_SAMPLES_SHAP': MAX_SAMPLES_SHAP,
        'SHAP_INTERACTIONS': SHAP_INTERACTIONS,
        'ANALYSIS_NAME': ANALYSIS_NAME,
        'PATH_TO_DATA': PATH_TO_DATA,
        'SHEET_NAME': SHEET_NAME,
        'OBJECTIVE': OBJECTIVE,
        'G_NAME': G_NAME,
        'X_CON_NAMES': X_CON_NAMES,
        'X_CAT_BIN_NAMES': X_CAT_BIN_NAMES,
        'X_CAT_MULT_NAMES': X_CAT_MULT_NAMES,
        'Y_NAMES': Y_NAMES,
        'SKIP_ROWS': SKIP_ROWS,
        'TEST_SET_IND': TEST_SET_IND,
        'path_to_results': path_to_results,
        'x_names': X_CON_NAMES+X_CAT_BIN_NAMES+X_CAT_MULT_NAMES,
        }

    # Create results directory ------------------------------------------------
    create_dir(path_to_results)

    # Copy this python script to results directory ----------------------------
    shutil.copy('iml_2_model.py', path_to_results+'/iml_2_model.py')

    # Load data ---------------------------------------------------------------
    # Load groups from excel file
    G = pd.read_excel(
        task['PATH_TO_DATA'],
        sheet_name=task['SHEET_NAME'],
        header=0,
        usecols=task['G_NAME'],
        dtype=np.float64,
        skiprows=task['SKIP_ROWS'])
    # Load predictors from excel file
    X = pd.read_excel(
        task['PATH_TO_DATA'],
        sheet_name=task['SHEET_NAME'],
        header=0,
        usecols=task['x_names'],
        dtype=np.float64,
        skiprows=task['SKIP_ROWS'])
    # Reindex x to x_names
    X = X.reindex(task['x_names'], axis=1)
    # Load targets from excel file
    Y = pd.read_excel(
        task['PATH_TO_DATA'],
        sheet_name=task['SHEET_NAME'],
        header=0,
        usecols=task['Y_NAMES'],
        dtype=np.float64,
        skiprows=task['SKIP_ROWS'])

    # Modelling and testing ---------------------------------------------------
    # Iterate over prediction targets (Y_NAMES)
    for i_y, y_name in enumerate(Y_NAMES):
        # Add prediction target index to task
        task['i_y'] = i_y
        # Add prediction target name to task
        task['y_name'] = [y_name]

        # Deal with NaNs in the target ----------------------------------------
        # Get current target and remove NaNs
        y = Y[y_name].to_frame().dropna()
        # Use y index for groups and reset index
        g = G.reindex(index=y.index).reset_index(drop=True)
        # Use y index for predictors and reset index
        x = X.reindex(index=y.index).reset_index(drop=True)
        # Reset index of target
        y = y.reset_index(drop=True)
        # Raise Warning if samples were dropped because of NaNs in target
        if y.shape[0] < Y.shape[0]:
            # Warning
            warnings.warn(
                'Warning: ' +
                str(Y.shape[0]-y.shape[0]) +
                ' samples were dropped due to NaNs in ' +
                y_name+'.', UserWarning)
        # Get target-encoding categories but don't do encoding ----------------
        # If multi categorical predictors
        if task['X_CAT_MULT_NAMES']:
            # Instatiate target-encoder
            te = TargetEncoder(
                categories='auto',
                target_type='continuous',
                smooth='auto',
                cv=5,
                shuffle=True,
                random_state=None)
            # Fit target-encoder
            te.fit(x[task['X_CAT_MULT_NAMES']], y.squeeze())
            # Get target-encoder categories
            task['te_categories'] = te.categories_
        # Other
        else:
            # Set target-encoder categories to empty
            task['te_categories'] = []

        # Run analysis --------------------------------------------------------
        # Cross-validation
        if TYPE == 'CV':
            # Run cross-validation
            cross_validation(task, g, x, y)
        # Switch Type of analysis
        elif TYPE == 'TT':
            # Run train-test split
            train_test_split(task, g, x, y)
        # Other
        else:
            # Raise error
            raise ValueError('Analysis type not found.')

    # Return None -------------------------------------------------------------
    return


if __name__ == '__main__':
    main()
