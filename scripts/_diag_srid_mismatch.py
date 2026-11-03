# -*- coding: utf-8 -*-
"""确认 target_srid 配置与 GeoServer 图层声明是否一致。"""
import json
import urllib.request

import psycopg

conn = psycopg.connect(
    host="127.0.0.1", port=15432, dbname="erlunyanbao",
    user="RurallandContractExtension", password="yt2rp9hGgtCVnPCZrCKCYF34",
)
cur = conn.cursor()
for sql, label in [
    ("SELECT key, value FROM system_config WHERE key ILIKE '%srid%' OR key ILIKE '%target%'", "system_config srid"),
    ("SELECT f_table_schema, f_table_name, f_geometry_column, srid FROM geometry_columns WHERE f_table_name='survey_dk_result'", "geometry_columns"),
]:
    try:
        cur.execute(sql)
        print(f"-- {label}: {cur.fetchall()}")
    except Exception as e:
        conn.rollback()
        print(f"-- {label}: ERROR {e}")
conn.close()

# GeoServer feature type 声明
url = "http://admin:geoserver@127.0.0.1:8080/geoserver/rest/workspaces/erlunyanbao/datastores/postgis/featuretypes/survey_dk_result.json"
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        ft = json.load(r)["featureType"]
    print("-- nativeName:", ft.get("nativeName"))
    print("-- srs:", ft.get("srs"))
    print("-- nativeBoundingBox:", json.dumps(ft.get("nativeBoundingBox"), ensure_ascii=False))
    print("-- latLonBoundingBox:", json.dumps(ft.get("latLonBoundingBox"), ensure_ascii=False))
    print("-- projectionPolicy:", ft.get("projectionPolicy"))
except Exception as e:
    print("-- geoserver REST ERROR:", e)
