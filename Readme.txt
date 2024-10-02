How to install (20240129)
(1)  Install git from: https://www.git-scm.com/downloads
(2)  Install miniconda from: https://docs.conda.io/projects/miniconda/en/latest/
(3)  Open anaconda prompt
(4)  Update conda: conda update conda
(5)  Setup new environment: conda create -n iml
(6)  Activate new environment: conda activate iml
(7)  Get packages: conda install -c conda-forge -n iml python=3.11 scikit-learn spyder ipywidgets matplotlib seaborn openpyxl lightgbm shap=*=cpu* blas=*=mkl

How to update (20240129)
(1)  Open anaconda prompt
(2)  Update packages: conda update -c conda-forge -n iml --all shap=*=cpu* blas=*=mkl

How to get developer version of shap (20240129)
(1)  Get shap: pip install git+https://github.com/shap/shap