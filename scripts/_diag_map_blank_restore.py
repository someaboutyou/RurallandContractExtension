# -*- coding: utf-8 -*-
"""诊断：还原现场数据后地图空白 / GetFeatureInfo 空。
查 survey_dk_result 行数、几何、区域分布；顺带看 fbf/cbf。"""
import json

import psycopg

conn = psycopg.connect(
    host="127.0.0.1", port=15432, dbname="erlunyanbao",
    user="RurallandContractExtension", password="yt2rp9hGgtCVnPCZrCKCYF34",
)
cur = conn.cursor()

def q(sql, label):
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"-- {label}: {rows}")
    except Exception as e:
        conn.rollback()
        print(f"-- {label}: ERROR {e}")

q("SELECT count(*) FROM survey_dk_result", "dk_result total")
q("SELECT count(*) FROM survey_dk_result WHERE geom IS NOT NULL", "dk_result with geom")
q("SELECT region_code, count(*) FROM survey_dk_result GROUP BY region_code ORDER BY 2 DESC LIMIT 8", "dk by region_code")
q("SELECT left(dkbm,6) dk_prefix, count(*) FROM survey_dk_result GROUP BY 1 ORDER BY 2 DESC LIMIT 8", "dkbm prefixes")
q("SELECT count(*) FROM survey_cbf_result", "cbf total")
q("SELECT count(*) FROM survey_fbf_result", "fbf total")
q("SELECT count(*) FROM survey_cbf_jtcy_result", "jtcy total")
q("SELECT count(*) FROM regions", "regions total")
q("SELECT count(*) FROM data_import_batches", "import batches")
q("SELECT ST_AsText(ST_Extent(geom)) FROM survey_dk_result", "dk geom extent")
q("SELECT DISTINCT ST_SRID(geom) FROM survey_dk_result LIMIT 3", "geom SRID")
conn.close()
