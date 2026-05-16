--
-- PostgreSQL database dump
--

\restrict yP9cg2DzdcNPocmslT4mCmUfYXyqTJhxeKGnWKhixVDWWl3TbqWY8qqQwlhOI0h

-- Dumped from database version 15.2
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cbdkxx; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbdkxx (
    dkbm character varying(19),
    fbfbm character varying(14),
    cbfbm character varying(18),
    cbjyqqdfs character varying(3),
    htmj numeric(15,2),
    cbhtbm character varying(19),
    lzhtbm character varying(18),
    cbjyqzbm character varying(19),
    yhtmj numeric(15,2),
    htmjm numeric(15,2),
    yhtmjm numeric(15,2),
    sfqqqg character varying(1)
);


--
-- Name: cbjyqz; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbjyqz (
    cbjyqzbm character varying(19),
    fzrq timestamp without time zone NOT NULL,
    qzsflq character varying(1),
    qzlqrq timestamp without time zone,
    qzlqrzjlx character varying(1),
    qzlqrzjhm character varying(20),
    fzjg character varying(50),
    qzlqrxm character varying(50)
);


--
-- Name: cbjyqz_qzbf; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbjyqz_qzbf (
    cbjyqzbm character varying(19),
    qzbfyy character varying(200),
    bfrq timestamp without time zone NOT NULL,
    qzbflqrq timestamp without time zone NOT NULL,
    qzbflqrxm character varying(50),
    bflqrzjlx character varying(1),
    bflqrzjhm character varying(20)
);


--
-- Name: cbjyqz_qzhf; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbjyqz_qzhf (
    cbjyqzbm character varying(19),
    qzhfyy character varying(200),
    hfrq timestamp without time zone NOT NULL,
    qzhflqrq timestamp without time zone NOT NULL,
    qzhflqrxm character varying(50),
    hflqrzjlx character varying(1),
    hflqrzjhm character varying(20)
);


--
-- Name: cbjyqz_qzzx; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbjyqz_qzzx (
    cbjyqzbm character varying(19),
    zxyy character varying(200),
    zxrq timestamp without time zone NOT NULL
);


--
-- Name: cbjyqzdjb; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cbjyqzdjb (
    cbjyqzbm character varying(19),
    fbfbm character varying(14),
    cbfbm character varying(18),
    cbfs character varying(3),
    cbqx character varying(30),
    cbqxq timestamp without time zone NOT NULL,
    cbqxz timestamp without time zone NOT NULL,
    dksyt character varying(255),
    cbjyqzlsh character varying(254),
    dbr character varying(50),
    djsj timestamp without time zone NOT NULL,
    djbfj character varying(254),
    ycbjyqzbh character varying(100)
);


--
-- Name: lzht; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lzht (
    cbhtbm character varying(19),
    lzhtbm character varying(18),
    cbfbm character varying(18),
    srfbm character varying(18),
    lzfs character varying(3),
    lzqx character varying(10),
    lzqxksrq timestamp without time zone NOT NULL,
    lzqxjsrq timestamp without time zone NOT NULL,
    lzmj numeric(15,2),
    lzdks integer NOT NULL,
    lzjgsm character varying(100),
    htqdrq timestamp without time zone NOT NULL
);


--
-- Name: qslyzlfj; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qslyzlfj (
    cbjyqzbm character varying(19),
    zlfjbh character varying(20),
    zlfjmc character varying(100),
    zlfjrq timestamp without time zone NOT NULL,
    fj character varying(254)
);


--
-- PostgreSQL database dump complete
--

\unrestrict yP9cg2DzdcNPocmslT4mCmUfYXyqTJhxeKGnWKhixVDWWl3TbqWY8qqQwlhOI0h

