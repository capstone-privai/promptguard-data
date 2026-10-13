import configparser

import boto3


def client():
    cfg = configparser.ConfigParser()
    cfg.read("config/storage.ini")
    return boto3.client("s3", region_name=cfg["s3"]["region"])  # credentials: environment
