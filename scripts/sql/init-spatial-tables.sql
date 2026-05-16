--
-- Spatial tables for GeoServer layer publishing
-- These tables are imported from GDB files and contain Chinese land management spatial data.
-- All tables use native PostGIS geometry columns.
--

CREATE EXTENSION IF NOT EXISTS postgis;

-- 村庄开发边界 (Village Construction Boundary)
CREATE TABLE IF NOT EXISTS public.czkfbj (
    "OBJECTID" int8 NOT NULL,
    "Shape" public.geometry(multipolygon, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "XZQDM" varchar(12) NULL,
    "XZQMC" varchar(100) NULL,
    "GHFQDM" varchar(3) NULL,
    "GHFQMC" varchar(50) NULL,
    "MJ" numeric NULL,
    "BZ" varchar(255) NULL,
    "Shape_Length" numeric NULL,
    "Shape_Area" numeric NULL,
    "MJ_YS" numeric NULL,
    "MJ_YS_DOUBLE" numeric NULL,
    "MJ_TQ" numeric NULL,
    CONSTRAINT czkfbj_pkey PRIMARY KEY ("OBJECTID")
);

-- 地类图斑 (Land Type Patch)
CREATE TABLE IF NOT EXISTS public.dltb (
    "OBJECTID" int8 NOT NULL,
    "Shape" public.geometry(multipolygon, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "TBYBH" varchar(18) NULL,
    "TBBH" varchar(8) NULL,
    "DLBM" varchar(5) NULL,
    "DLMC" varchar(60) NULL,
    "QSXZ" varchar(2) NULL,
    "QSDWDM" varchar(19) NULL,
    "ZLDWDM" varchar(19) NULL,
    "ZLDWMC" varchar(255) NULL,
    "TBMJ" numeric NULL,
    "KCDLBM" varchar(5) NULL,
    "KCXS" numeric NULL,
    "KCMJ" numeric NULL,
    "TBDLMJ" numeric NULL,
    "GDLX" varchar(2) NULL,
    "GDPDJB" varchar(2) NULL,
    "XZDWKD" numeric NULL,
    "TBXHMC" varchar(100) NULL,
    "ZZSXDM" varchar(30) NULL,
    "ZZSXMC" varchar(100) NULL,
    "GDDB" int4 NULL,
    "FRDBS" varchar(1) NULL,
    "CZCSXM" varchar(4) NULL,
    "SJNF" int4 NULL,
    "MSSM" varchar(2) NULL,
    "HDMC" varchar(100) NULL,
    "BZ" varchar(255) NULL,
    "TBXHDM" varchar(30) NULL,
    "Shape_Length" numeric NULL,
    "Shape_Area" numeric NULL,
    CONSTRAINT dltb_pkey PRIMARY KEY ("OBJECTID")
);

-- 耕地保护目标 (Farmland Protection Target)
CREATE TABLE IF NOT EXISTS public.gdbhmb (
    "OBJECTID" int8 NOT NULL,
    "Shape" public.geometry(multipolygon, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "TBYBH" varchar(18) NULL,
    "TBBH" varchar(8) NULL,
    "DLBM" varchar(5) NULL,
    "DLMC" varchar(60) NULL,
    "QSXZ" varchar(2) NULL,
    "QSDWDM" varchar(19) NULL,
    "QSDWMC" varchar(255) NULL,
    "ZLDWDM" varchar(19) NULL,
    "ZLDWMC" varchar(255) NULL,
    "TBMJ" numeric NULL,
    "KCDLBM" varchar(5) NULL,
    "KCXS" numeric NULL,
    "KCMJ" numeric NULL,
    "TBDLMJ" numeric NULL,
    "GDLX" varchar(2) NULL,
    "SFWHTD" int4 NULL,
    "GDPDJB" varchar(2) NULL,
    "TBXHDM" varchar(6) NULL,
    "TBXHMC" varchar(20) NULL,
    "ZZSXDM" varchar(6) NULL,
    "ZZSXMC" varchar(20) NULL,
    "GDDB" int4 NULL,
    "FRDBS" varchar(1) NULL,
    "SJNF" int4 NULL,
    "ORIG_FID" int4 NULL,
    "TBMJ_YS" numeric NULL,
    "TBDLMJ_YS" numeric NULL,
    "KCMJ_YS" numeric NULL,
    "Shape_Length" numeric NULL,
    "Shape_Area" numeric NULL,
    CONSTRAINT gdbhmb_pkey PRIMARY KEY ("OBJECTID")
);

-- 生态保护红线 (Ecological Protection Redline)
CREATE TABLE IF NOT EXISTS public.stbhhx (
    "OBJECTID" int8 NOT NULL,
    "Shape" public.geometry(multipolygon, 4490) NULL,
    "BSM" varchar(255) NULL,
    "YSDM" varchar(255) NULL,
    "XZQDM" varchar(255) NULL,
    "XZQMC" varchar(255) NULL,
    "SHENG" varchar(255) NULL,
    "SHI" varchar(255) NULL,
    "XIAN" varchar(255) NULL,
    "HXBM" varchar(255) NULL,
    "HXMC" varchar(255) NULL,
    "HXLX" varchar(255) NULL,
    "LXBM" varchar(255) NULL,
    "MJ" numeric NULL,
    "ZRBHDMC" varchar(255) NULL,
    "ZRBHDJB" varchar(255) NULL,
    "ZRBHDLX" varchar(255) NULL,
    "ZRBHDFQ" varchar(255) NULL,
    "XTYZBLX" varchar(255) NULL,
    "GKCS" varchar(255) NULL,
    "SZXJXZQDM" varchar(255) NULL,
    "SZXJXZQMC" varchar(255) NULL,
    "BZ" varchar(255) NULL,
    "MJ_YS" numeric NULL,
    "MJ_YS_DOUBLE" numeric NULL,
    "MJ_TQ" numeric NULL,
    "Shape_Length" numeric NULL,
    "Shape_Area" numeric NULL,
    CONSTRAINT stbhhx_pkey PRIMARY KEY ("OBJECTID")
);

-- 行政区 (Administrative District)
CREATE TABLE IF NOT EXISTS public.xzq (
    "OBJECTID" int8 NOT NULL,
    "SHAPE" public.geometry(multipolygon, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "XZQDM" varchar(9) NULL,
    "XZQMC" varchar(100) NULL,
    "DCMJ" numeric NULL,
    "JSMJ" numeric NULL,
    "MSSM" varchar(2) NULL,
    "HDMC" varchar(100) NULL,
    "BZ" varchar(255) NULL,
    "SHAPE_Length" numeric NULL,
    "SHAPE_Area" numeric NULL,
    CONSTRAINT xzq_pkey PRIMARY KEY ("OBJECTID")
);

-- 行政区界线 (Administrative Boundary Lines)
CREATE TABLE IF NOT EXISTS public.xzqjx (
    "OBJECTID" int8 NOT NULL,
    "SHAPE" public.geometry(multilinestring, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "JXLX" varchar(6) NULL,
    "JXXZ" varchar(6) NULL,
    "JXSM" varchar(100) NULL,
    "BZ" varchar(255) NULL,
    "SHAPE_Length" numeric NULL,
    CONSTRAINT xzqjx_pkey PRIMARY KEY ("OBJECTID")
);

-- 永久基本农田保护图斑 (Permanent Basic Farmland Protection Patch)
CREATE TABLE IF NOT EXISTS public.yjjbntbhtb (
    "OBJECTID" int8 NOT NULL,
    "Shape" public.geometry(multipolygon, 4527) NULL,
    "BSM" varchar(18) NULL,
    "YSDM" varchar(10) NULL,
    "XZQDM" varchar(12) NULL,
    "XZQMC" varchar(100) NULL,
    "YJJBNTTBBH" varchar(20) NULL,
    "TBBH" varchar(8) NULL,
    "DLBM" varchar(5) NULL,
    "DLMC" varchar(60) NULL,
    "QSXZ" varchar(2) NULL,
    "QSDWDM" varchar(19) NULL,
    "ZLDWDM" varchar(19) NULL,
    "YJJBNTTBMJ" numeric NULL,
    "KCDLBM" varchar(5) NULL,
    "KCXS" numeric NULL,
    "KCMJ" numeric NULL,
    "YJJBNTMJ" numeric NULL,
    "GDLX" varchar(2) NULL,
    "GDPDJB" varchar(2) NULL,
    "GGBZL" varchar(10) NULL,
    "TBXHDM" varchar(6) NULL,
    "TBXHMC" varchar(20) NULL,
    "ZZSXDM" varchar(6) NULL,
    "ZZSXMC" varchar(20) NULL,
    "GDDB" int4 NULL,
    "GDDJ" int4 NULL,
    "ZLFLDM" varchar(12) NULL,
    "FRDBS" varchar(1) NULL,
    "SJNF" int4 NULL,
    "CFZR" varchar(20) NULL,
    "ZMC" varchar(50) NULL,
    "ZZRR" varchar(20) NULL,
    "ZRRZJHM" varchar(18) NULL,
    "ZRRMC" varchar(20) NULL,
    "LXDH" varchar(20) NULL,
    "JZDZ" varchar(50) NULL,
    "BHKSSJ" timestamp NULL,
    "BHJSSJ" timestamp NULL,
    "SJBH" varchar(20) NULL,
    "SJMC" varchar(50) NULL,
    "ZRSYX" varchar(100) NULL,
    "WDGD" varchar(10) NULL,
    "SFWYYJJBNT" varchar(10) NULL,
    "BZ" varchar(50) NULL,
    "QSDWMC" varchar(255) NULL,
    "ZLDWMC" varchar(255) NULL,
    "FWDGDHRLY" varchar(255) NULL,
    "ORIG_FID" int4 NULL,
    "YJJBNTTBMJ_YS" numeric NULL,
    "YJJBNTMJ_YS" numeric NULL,
    "KCMJ_YS" numeric NULL,
    "Shape_Length" numeric NULL,
    "Shape_Area" numeric NULL,
    "WDGD_YS" varchar(10) NULL,
    CONSTRAINT yjjbntbhtb_pkey PRIMARY KEY ("OBJECTID")
);

CREATE INDEX IF NOT EXISTS ix_czkfbj_shape_gist
ON public.czkfbj USING GIST ("Shape")
WHERE "Shape" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_dltb_shape_gist
ON public.dltb USING GIST ("Shape")
WHERE "Shape" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_gdbhmb_shape_gist
ON public.gdbhmb USING GIST ("Shape")
WHERE "Shape" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_stbhhx_shape_gist
ON public.stbhhx USING GIST ("Shape")
WHERE "Shape" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_xzq_shape_gist
ON public.xzq USING GIST ("SHAPE")
WHERE "SHAPE" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_xzqjx_shape_gist
ON public.xzqjx USING GIST ("SHAPE")
WHERE "SHAPE" IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_yjjbntbhtb_shape_gist
ON public.yjjbntbhtb USING GIST ("Shape")
WHERE "Shape" IS NOT NULL;
