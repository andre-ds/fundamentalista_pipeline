from distutils.log import error
import os
import re
import urllib.request
from datetime import datetime, date, timedelta
from airflow import DAG
from groups.group_extractions_cvm import extraction_cvm_itr, extraction_cvm_dfp
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook


# Exemplo de definição de schedule 
# .---------------- minuto (0 - 59)
# |  .------------- hora (0 - 23)
# |  |  .---------- dia do mês (1 - 31)
# |  |  |  .------- mês (1 - 12) 
# |  |  |  |  .---- dia da semana (0 - 6) (Domingo=0 or 7)
# |  |  |  |  |
# *  *  *  *  * (nome do usuário que vai executar o comando)

DIR_PATH = os.path.dirname(os.path.realpath('__file__'))
years_list = [*range(2011, 2023, 1)]


def _path_environment(ti):
    
    import os
    DIR_PATH = os.path.dirname(os.path.realpath('__file__'))
    list_folders = os.listdir(DIR_PATH)
    if 'datalake' not in list_folders:
        os.mkdir(os.path.join(DIR_PATH, 'datalake'))
    
    PATH_DATALAKE = os.path.join(DIR_PATH, 'datalake')
    # Creating temp folders
    list_folders = os.listdir(PATH_DATALAKE)
    if 'raw' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'raw'))
    if 'pre-processed' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'pre-processed'))
    if 'zipfiles' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'zipfiles'))
    if 'unzippedfiles' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'unzippedfiles'))
    if 'analytical' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'analytical'))
    if 'auxiliary' not in list_folders:
        os.mkdir(os.path.join(PATH_DATALAKE, 'auxiliary'))
        
    DIR_PATH_RAW = os.path.join(PATH_DATALAKE, 'raw')
    ti.xcom_push(key='DIR_PATH_RAW', value=DIR_PATH_RAW)

'''
def _extraction_raw(dataType:str, years_list:list):
    
    todaystr = re.sub('-', '_', str((date.today())))
    DIR_PATH_RAW = os.path.join(os.path.join(DIR_PATH, 'datalake'), 'raw')
    repository_registration = 'http://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv'
    repository_DFP = 'http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/'
    repository_ITR = 'http://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/'

    if 'registration' in dataType:
            urllib.request.urlretrieve(repository_registration, os.path.join(DIR_PATH_RAW, 'extracted_{todaystr}_cad_cia_aberta.csv'))

    for year in years_list:
        # Year (yearly)
        if 'dfp' in dataType:
            urllib.request.urlretrieve(repository_DFP+f'dfp_cia_aberta_{year}.zip', os.path.join(DIR_PATH_RAW, f'extracted_{todaystr}_dfp_cia_aberta_{year}.zip'))
        # Quarter (quarterly) 
        if 'itr' in dataType:
            try:
                urllib.request.urlretrieve(repository_ITR+f'itr_cia_aberta_{year}.zip', os.path.join(DIR_PATH_RAW, f'extracted_{todaystr}_itr_cia_aberta_{year}.zip'))
            except:
                print('error')
'''

def _load_bucket(bucket, DIR_PATH):

    hook = S3Hook('s3_conn')
    DIR_PATH_RAW = os.path.join(os.path.join(DIR_PATH, 'datalake'), 'raw')
    files_foder = [file for file in os.listdir(DIR_PATH_RAW)]
    for file in files_foder:
        hook.load_file(filename=os.path.join(DIR_PATH_RAW, f'{file}'), bucket_name=bucket, key=f'{file}')

# '*/50 * * * *'
with DAG(
    dag_id='extraction_cvm',
    start_date=datetime(2022, 8, 9),
    schedule_interval='@daily',
    catchup=False
) as dag:

    environment = PythonOperator(
        task_id='path_environment',
        python_callable=_path_environment,
        op_kwargs={'path':DIR_PATH}
    )

    ext_cvm_dfp = extraction_cvm_dfp()
    ext_cvm_itr = extraction_cvm_itr()

    upload_s3 = PythonOperator(
        task_id='upload_s3_raw',
        python_callable=_load_bucket,
        op_kwargs={
            'bucket':'deepfi-raw',
            'DIR_PATH': DIR_PATH
        }
    )

environment >> [ext_cvm_dfp, ext_cvm_itr] >> upload_s3