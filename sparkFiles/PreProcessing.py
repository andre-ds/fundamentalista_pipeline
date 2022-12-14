import os
import re
from datetime import date
from pyspark.sql.window import Window
from pyspark.sql import DataFrame, udf
from pyspark.sql.types import StructField, StructType, DateType, DoubleType, StringType, IntegerType, FloatType
from pyspark.sql.functions import col, quarter, to_date, month, year, when, to_date, asc, months_between, round, concat, lit, regexp_replace, mean, stddev, variance, sum, min, max, lag, collect_list, slice, row_number, abs
from pyspark.sql.window import Window


class PreProcessing():


    def __init__(self, spark_environment):
        self._run()
        self.spark_environment = spark_environment


    def _run(self):

        self.todaystr = re.sub('-', '_', str((date.today())))


    def remove_missing_values(self, dataset:DataFrame) -> DataFrame:

        missing_variables = {col: dataset.filter(dataset[col].isNull()).count() for col in dataset.columns}

        return missing_variables


    def text_normalization(row):

        return row.encode('ascii', 'ignore').decode('ascii')


    def patterning_text_var(self, dataset:DataFrame, variable:str) -> DataFrame:

        dataset[variable] = dataset[variable].str.lower().str.strip().str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
        dataset[variable] = dataset[variable].replace(r'\s+', '_', regex=True)

        return dataset


    def files_list(self, type_file):
        
        #years_list = [*range(2011, date.today().year+1, 1)]
        years_list = [*range(2011, 2023, 1)]
        files_list = []
        for y in years_list:
            if type_file == 'itr_itr_dfp':
                zip_files = [f'pp_itr_dre_{y}.parquet', f'pp_dfp_dre_{y}.parquet']
            elif type_file == 'dfp_all':
                zip_files = [ f'pp_dfp_dre_{y}.parquet', f'pp_dfp_bpa_{y}.parquet', f'pp_dfp_bpp_{y}.parquet']
            elif type_file == 'itr_all':
                zip_files = [ f'pp_itr_dre_{y}.parquet', f'pp_itr_bpa_{y}.parquet', f'pp_itr_bpp_{y}.parquet']
            files_list.append(zip_files)

        return files_list


    def _union_quarters(self, dataset_itr:DataFrame, dataset_dfp:DataFrame) -> DataFrame:

        # Agregations Q1, Q2 and Q3
        df_sum = dataset_itr.groupBy(['processed_at', 'id_cvm', 'id_cnpj', 'txt_company_name', 'dt_year']).agg(
            lit(None).alias('dt_refer'),
            lit(None).alias('dt_fim_exerc'),
            lit(None).alias('dt_ini_exerc'),
            lit(None).alias('dt_quarter'),
            sum('amt_cost_goods_and_services').alias('amt_cost_goods_and_services'), \
            sum('amt_earnings_before_income_tax_and_social_contribution').alias('amt_earnings_before_income_tax_and_social_contribution'), \
            sum('amt_earnings_before_interest_and_taxes').alias('amt_earnings_before_interest_and_taxes'), \
            sum('amt_financial_results').alias('amt_financial_results'), \
            sum('amt_groos_revenue').alias('amt_groos_revenue'), \
            sum('amt_net_profit').alias('amt_net_profit'), \
            sum('amt_operating_revenues_and_expenses').alias('amt_operating_revenues_and_expenses'), \
            sum('amt_sales_revenue').alias('amt_sales_revenue'))

        # Changing sinal for sumation
        varlist = ['amt_cost_goods_and_services', 'amt_earnings_before_income_tax_and_social_contribution',
        'amt_earnings_before_interest_and_taxes', 'amt_financial_results', 'amt_groos_revenue',
        'amt_net_profit', 'amt_operating_revenues_and_expenses', 'amt_sales_revenue']
        for v in varlist:
            df_sum = df_sum.withColumn(v, -col(v))

        # Union and sum datasets
        dataset_q4 = dataset_dfp.union(df_sum.select(dataset_dfp.columns))
        dataset_q4 = dataset_q4.groupBy(['processed_at', 'id_cvm', 'id_cnpj', 'txt_company_name', 'dt_year']).agg(
            max('dt_refer').alias('dt_refer'), \
            max('dt_fim_exerc').alias('dt_fim_exerc'), \
            max('dt_ini_exerc').alias('dt_ini_exerc'), \
            max('dt_quarter').alias('dt_quarter'), \
            sum('amt_cost_goods_and_services').alias('amt_cost_goods_and_services'), \
            sum('amt_earnings_before_income_tax_and_social_contribution').alias('amt_earnings_before_income_tax_and_social_contribution'), \
            sum('amt_earnings_before_interest_and_taxes').alias('amt_earnings_before_interest_and_taxes'), \
            sum('amt_financial_results').alias('amt_financial_results'), \
            sum('amt_groos_revenue').alias('amt_groos_revenue'), \
            sum('amt_net_profit').alias('amt_net_profit'), \
            sum('amt_operating_revenues_and_expenses').alias('amt_operating_revenues_and_expenses'), \
            sum('amt_sales_revenue').alias('amt_sales_revenue'))

        # Union with quarters datasets
        dataset = dataset_itr.union(dataset_q4.select(dataset_itr.columns))

        return dataset


    def _pre_processing_itr_dre(self, dataset:DataFrame) -> DataFrame:
    
        from sparkDocuments import dre_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping last registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc', 'dt_ini_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_months_exercise', round(months_between(col('dt_fim_exerc'), col('dt_ini_exerc'))))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        dataset = dataset.filter(col('dt_months_exercise') == 3)
        ## Standarting escala_moeda
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(dre_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        ## Standarting CD_CONTA
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', dre_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_refer', 'dt_fim_exerc', 'dt_ini_exerc', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm', 'id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset


    def _pre_processing_itr_bpp(self, dataset:DataFrame) -> DataFrame:
        
        from sparkDocuments import bpp_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping las registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        ## Standarting ESCALA_MOEDA
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(bpp_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', bpp_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm','id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset
        

    def _pre_processing_itr_bpa(self, dataset:DataFrame) -> DataFrame:

        from sparkDocuments import bpa_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping las registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        ## Standarting ESCALA_MOEDA
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(bpa_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', bpa_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm','id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset


    def _pre_processing_dfp_dre(self, dataset:DataFrame) -> DataFrame:

        from sparkDocuments import dre_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping last registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc', 'dt_ini_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_months_exercise', round(months_between(col('dt_fim_exerc'), col('dt_ini_exerc'))))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        dataset = dataset.filter(col('dt_months_exercise') == 12)
        ## Standarting escala_moeda
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(dre_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        ## Standarting CD_CONTA
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', dre_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_refer', 'dt_fim_exerc', 'dt_ini_exerc', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm', 'id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset


    def _pre_processing_dfp_bpa(self, dataset:DataFrame) -> DataFrame:

        from sparkDocuments import bpa_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping las registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        ## Standarting escala_moeda
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(bpa_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', bpa_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm','id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset


    def _pre_processing_dfp_bpp(self, dataset:DataFrame) -> DataFrame:

        from sparkDocuments import bpp_account

        # Pre-processing
        for var in dataset.columns:
            dataset = dataset.withColumnRenamed(var, var.lower())
        # Keeping las registers
        dataset = dataset.filter(col('ordem_exerc') == '??LTIMO')
        ## Getting year and quarter
        for v in ['dt_refer', 'dt_fim_exerc']:
            dataset = dataset.withColumn(v, to_date(col(v), 'yyyy-MM-dd'))
        dataset = dataset.withColumn('dt_year', year('dt_refer'))
        dataset = dataset.withColumn('dt_quarter', quarter('dt_refer'))
        ## Standarting escala_moeda
        dataset = dataset.withColumn('vl_conta', when(col('escala_moeda') == 'MIL', col('vl_conta')*1000).otherwise(col('vl_conta')))
        ## Keeping only relevants cd_conta
        listKey = list(bpp_account.keys())
        dataset = dataset.filter(col('cd_conta').isin(listKey))
        for k in listKey:
            dataset = dataset.withColumn('cd_conta', regexp_replace('cd_conta', '^' + k + '$', bpp_account.get(k)))
        # Pivot dataset
        varlist = ['cd_cvm', 'cnpj_cia', 'denom_cia', 'dt_year', 'dt_quarter']
        dataset = dataset.groupBy(varlist).pivot('cd_conta').max('vl_conta').na.fill(0)
        # Rename all variables to upercase
        variablesRename = [['cd_cvm','id_cvm'], ['cnpj_cia', 'id_cnpj'], ['denom_cia','txt_company_name']]
        for v in variablesRename:
            dataset = dataset.withColumnRenamed(v[0], v[1])

        return dataset


    def pre_process_cvm(self, dataType:str, schema:StructField, year:str, execution_date:DateType):


        from sparkDocuments import types_dict, DIR_PATH_RAW_DFP, DIR_PATH_RAW_ITR, DIR_PATH_PROCESSED_DFP, DIR_PATH_PROCESSED_ITR


        def _saving_pre_processing(dataset, path, dataType, file):
                #.partitionBy('id_cvm')
            saveFilename = f'pp_{dataType}_{file[-8:-4]}.parquet'
            dataset.write.format('parquet') \
                .mode('overwrite') \
                .save(os.path.join(path, saveFilename)) 

        def _processed_date(dataset, execution_date):
            dataset = (
             dataset
             .withColumn('processed_at', lit(execution_date))
             .withColumn('processed_at', to_date(col('processed_at'), 'yyyy-MM-dd'))
            )
       
            return dataset


        if dataType == 'itr_dre' or dataType == 'itr_bpp' or dataType == 'itr_bpa':
            list_files = [file for file in os.listdir(DIR_PATH_RAW_ITR) if (file.endswith('.csv')) and re.findall(types_dict[dataType], file)]
        elif dataType == 'dfp_dre' or dataType == 'dfp_bpp' or dataType == 'dfp_bpa':
            list_files = [file for file in os.listdir(DIR_PATH_RAW_DFP) if (file.endswith('.csv')) and re.findall(types_dict[dataType], file)]


        for file in list_files:
            if year == file[-8:-4]:
                # Oppen Datasets
                if dataType == 'itr_dre':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_ITR, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_itr_dre(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_ITR)
                elif dataType == 'itr_bpp':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_ITR, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_itr_bpp(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)                   
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_ITR)
                elif dataType == 'itr_bpa':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_ITR, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_itr_bpa(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)        
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_ITR)
                elif dataType == 'dfp_dre':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_DFP, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_dfp_dre(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_DFP)
                elif dataType == 'dfp_bpp':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_DFP, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_dfp_bpp(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_DFP)
                elif dataType == 'dfp_bpa':
                    dataset = self.spark_environment.read.csv(os.path.join(DIR_PATH_RAW_DFP, file), header = True, sep=';', encoding='ISO-8859-1', schema=schema)
                    dataset = self._pre_processing_dfp_bpa(dataset = dataset)
                    dataset = _processed_date(dataset=dataset, execution_date=execution_date)
                    _saving_pre_processing(dataset=dataset, dataType=dataType, file=file, path=DIR_PATH_PROCESSED_DFP)


    def get_lag(self, dataset:DataFrame, partition_var:list, order_var:list, type:str, measure:str, variable:str, nlag:int, period:int=None, period_text:str=None) -> DataFrame:

        windowSpec  = Window.partitionBy(partition_var).orderBy(order_var)

        if period_text is not None:
            dataset = dataset.withColumn(f'{type}_{measure}_{variable}_{period_text}_lag',lag(variable, nlag).over(windowSpec))
        else:
            dataset = dataset.withColumn(f'{type}_{measure}_{variable}_{nlag}{period}_lag',lag(variable, nlag).over(windowSpec))

        return dataset


    def get_percentage_change(self, dataset:DataFrame, partition_var:list, order_var:list, variable:str, nlag:int, period:int=None, period_text:str=None):

        windowSpec  = Window.partitionBy(partition_var).orderBy(order_var)
    
        if period_text is not None:
            dataset = (
                dataset
                .withColumn('var_lag',lag(variable, nlag).over(windowSpec))
                .withColumn(f'pct_tx_{variable}_{period_text}', (col(variable)-col('var_lag'))/abs(col('var_lag')))
                .drop('var_lag')
            )       
        else:
            dataset = (
                dataset
                .withColumn('var_lag',lag(variable, nlag).over(windowSpec))
                .withColumn(f'pct_tx_{variable}_{nlag}{period}', (col(variable)-col('var_lag'))/abs(col('var_lag')))
                .drop('var_lag')
            )

        return dataset


    def measure_run(self, dataset:DataFrame, partition_var:list, order_var:list, variable:str, n_periods:int, measure_type:str) -> DataFrame:

        WindowSpec = Window.partitionBy(partition_var).orderBy(order_var).rowsBetween(-n_periods, Window.currentRow)

        if measure_type == 'mean':
            variable_name = f'amt_avg_{variable}_{n_periods}'
            dataset = dataset.withColumn(variable_name, mean(col(variable)).over(WindowSpec))
        elif measure_type == 'std':
            variable_name = f'amt_std_{variable}_{n_periods}'
            dataset = dataset.withColumn(variable_name, stddev(col(variable)).over(WindowSpec))
        elif measure_type == 'var':
            variable_name = f'amt_var_{variable}_{n_periods}'
            dataset = dataset.withColumn(variable_name, variance(col(variable)).over(WindowSpec))
        elif measure_type == 'min':
            variable_name = f'amt_min_{variable}_{n_periods}'
            dataset = dataset.withColumn(variable_name, min(col(variable)).over(WindowSpec))
        elif measure_type == 'max':
            variable_name = f'amt_max_{variable}_{n_periods}'
            dataset = dataset.withColumn(variable_name, max(col(variable)).over(WindowSpec))

        return dataset


    def measure_beta(self, dataset:DataFrame, partition_var:list, order_var:list, variable:str, n_periods:int) -> DataFrame:

        windowSpec1  = Window.partitionBy(partition_var).orderBy(order_var)
        windowSpec2 = Window.partitionBy(partition_var).orderBy(order_var).rowsBetween(-n_periods, Window.currentRow)

        variable_name = f'amt_beta_{variable}_{n_periods+1}'

        dataset = (
            dataset
            .withColumn('y', lag(variable, 1).over(windowSpec1))
            .withColumn('y_mean', mean(col('y')).over(windowSpec2))
            .withColumn('y_y_mean', col(variable)-col('y_mean'))
            .withColumn('x_mean', mean(col(variable)).over(windowSpec2))
            .withColumn('x_x_mean', col(variable)-col('x_mean'))
            .withColumn('num', col('x_x_mean')*col('y_y_mean'))
            .withColumn('den', col('x_x_mean')*col('x_x_mean'))
            .withColumn(variable_name, col('num')/col('den'))
            .drop('y', 'y_mean', 'y_y_mean', 'x_mean', 'x_x_mean', 'num', 'den')
        )

        return dataset


    def broken_stock_high(self, dataset:DataFrame, variable:str, partition_variables:list, order_variables:list, n_periods:int) -> DataFrame:

        WindowSpec = Window.partitionBy(partition_variables).orderBy(order_variables).rowsBetween(-n_periods, -1)

        dataset = (
            dataset
            .withColumn('max', max(col(variable)).over(WindowSpec))
            .withColumn(f'cat_{variable}_broke_high_{n_periods}', when(col(variable) > col('max'), 1).otherwise(0))
            .drop('max')
        )

        return dataset


    def broken_stock_low(self, dataset:DataFrame, variable:str, partition_variables:list, order_variables:list, n_periods:int) -> DataFrame:

        WindowSpec = Window.partitionBy(partition_variables).orderBy(order_variables).rowsBetween(-n_periods, -1)

        dataset = (
            dataset
            .withColumn('min', min(col(variable)).over(WindowSpec))
            .withColumn(f'cat_{variable}_broke_low_{n_periods}', when(col(variable) > col('min'), 1).otherwise(0))
            .drop('min')
        )

        return dataset

    def IFR(self, dataset:DataFrame, partition_var:list, order_var:list, n_periods:int, variable:str):

        dataset = self.get_percentage_change(dataset=dataset, partition_var=partition_var, order_var=order_var, variable=variable, nlag=1, period='d')
   
        WindowSpec = Window.partitionBy(partition_var).orderBy(order_var).rowsBetween(start=-n_periods, end=-1)
        dataset = (
            dataset
            .withColumnRenamed(f'pct_tx_{variable}_1d','pct')
            .withColumn('high_price_mean', when(col('pct')>0, mean(col(variable)).over(WindowSpec)))
            .withColumn('low_price_mean', when(col('pct')<0, mean(col(variable)).over(WindowSpec)))
            .fillna(subset=['high_price_mean', 'low_price_mean'], value=0)
            .withColumn('high_price_mean', sum(col('high_price_mean')).over(WindowSpec))
            .withColumn('low_price_mean', sum(col('low_price_mean')).over(WindowSpec))
            .withColumn(f'amt_IFR_{variable}_{n_periods}', (100-(100/(1+(col('high_price_mean')/col('low_price_mean'))))))
            .drop('pct', 'high_price_mean', 'low_price_mean')
        )

        return dataset