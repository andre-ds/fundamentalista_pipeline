import os
import argparse
from pyspark.context import SparkContext
from pyspark.conf import SparkConf
from pyspark.sql import SparkSession
from PreProcessing import PreProcessing
from sparkDocuments import schema_dre

if __name__ == "__main__":
  
    parser = argparse.ArgumentParser(
        description="Spark Pre-processing"
    )
    parser.add_argument("--dataType", required=True)
    parser.add_argument("--years_list", required=True)
    args = parser.parse_args()


    sk = SparkSession(SparkContext(conf=SparkConf())\
        .getOrCreate())
        
    pp = PreProcessing(spark_environment=sk)
    if args.dataType == 'itr_dre':
        pp.pre_process_cvm(dataType=args.dataType, year=args.years_list, schema=schema_dre)
    