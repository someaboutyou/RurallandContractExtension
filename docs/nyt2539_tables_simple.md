# NY/T 2539-2016 ?????

???`datas/NYT2539-2016??????????????????.docx`

????????????????????

## ???

- `CBDKXX`: ?B.1 ??????
- `FBF`: ?B.2 ???
- `CBF`: ?B.3 ???
- `CBF_JTCY`: ?B.4 ????
- `CBHT`: ?B.5 ????
- `LZHT`: ?B.6 ????
- `QSLYZLFJ`: ?B.7 ????????
- `CBJYQZDJB`: ?B.8 ?????????
- `CBJYQZ`: ?B.9 ??????
- `CBJYQZ_QZBF`: ?B.10 ????
- `CBJYQZ_QZHF`: ?B.11 ????
- `CBJYQZ_QZZX`: ?B.12 ????

## ?B.1 `CBDKXX` ??????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|地块代码|DKBM|Char|19||非空|M|
|发包方代码a|FBFBM|Char|14||非空|M|
|承包方代码a|CBFBM|Char|18||非空|M|
|承包经营权取得方式|CBJYQQDFS|Char|3||见表C.10|M|
|合同面积b|HTMJ|Float|15|2|非空|M|
|承包合同代码a|CBHTBM|Char|18||非空|M|
|流转合同代码c|LZHTBM|Char|20||非空|O|
|承包经营权证（登记薄）代码a|CBJYQZBM|Char|19||非空|M|
|原合同面积|YHTMJ|Float|15|2|>0||
|确权（合同）面积（亩）|HTMJM|Float|15|2|>0|O|
|原合同面积（亩）|YHTMJM|Float|15|2|>0||
|是否确权确股|SFQQQG|Char|1|||O|

## ?B.2 `FBF` ???

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|发包方代码|FBFBM|Char|14||非空|M|
|发包方名称|FBFMC|Char|50||非空|M|
|发包方负责人姓名|FBFFZRXM|Char|50||非空|M|
|负责人证件类型|FZRZJLX|Char|1||见表C.15|M|
|负责人证件号码|FZRZJHM|Char|30||非空|M|
|联系电话|LXDH|Char|15||非空|O|
|发包方地址|FBFDZ|Char|100||非空|M|
|邮政代码|YZBM|Char|6||非空|M|
|发包方调查员|FBFDCY|Char|254||非空|M|
|发包方调查日期|FBFDCRQ|Date|8||YYYYMMDD|M|
|发包方调查记事|FBFDCJS|Char|254||非空|C|

## ?B.3 `CBF` ???

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包方代码|CBFBM|Char|18||非空|M|
|承包方类型|CBFLX|Char|1||见表C.16|M|
|承包方(代表)名称a|CBFMC|Char|50||非空|M|
|承包方(代表)证件类型a|CBFZJLX|Char|1||见表C.15|M|
|承包方(代表)证件号码a|CBFZJHM|Char|20||非空|M|
|承包方地址a|CBFDZ|Char|100||非空|M|
|邮政代码a|YZBM|Char|6||非空|M|
|联系电话a|LXDH|Char|20||非空|O|
|承包方成员数量b|CBFCYSL|Int|2||＞0|M|
|承包方调查日期|CBFDCRQ|Date|8||YYYYMMDD|M|
|承包方调查员|CBFDCY|Char|50||非空|M|
|承包方调查记事|CBFDCJS|Char|254||非空|C/有调查记事？|
|公示记事c|GSJS|Char|254||非空|C/有公示记事？|
|公示记事人c|GSJSR|Char|50||非空|M|
|公示审核日期c|GSSHRQ|Date|8||YYYYMMDD|M|
|公示审核人c|GSSHR|Char|50||非空|M|

## ?B.4 `CBF_JTCY` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包方代码|CBFBM|Char|18||非空|M|
|成员姓名|CYXM|Char|50||非空|M|
|成员性别|CYXB|Char|1||见表C.17|M|
|成员证件类型|CYZJLX|Char|1||见表C.15|M|
|成员证件号码|CYZJHM|Char|20||非空|M|
|与户主关系|YHZGX|Char|2||非空a|M|
|成员备注|CYBZ|Char|1||见表C.18|O|
|是否共有人b|SFGYR|Char|1||见表C.19|O|
|成员备注说明|CYBZSM|Char|254||非空|O|

## ?B.5 `CBHT` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包合同代码|CBHTBM|Char|19||非空|M|
|原承包合同代码|YCBHTBM|Char|19||非空|C/有原始承包合同？|
|发包方代码|FBFBM|Char|14||非空|M|
|承包方代码|CBFBM|Char|18||非空|M|
|承包方式|CBFS|Char|3||见表C.10|M|
|承包期限起|CBQXQ|Date|8||YYYYMMDD|M|
|承包期限止|CBQXZ|Date|8||YYYYMMDD|M|
|承包合同总面积|HTZMJ|Float|15|2|＞0|M|
|承包地块总数|CBDKZS|Int|3||＞0|M|
|签订时间|QDSJ|Date|8||YYYYMMDD|M|
|确权（合同）总面积（亩）|HTZMJM|Float|15|2|＞0|O|
|原合同总面积|YHTZMJ|Float|15|2|＞0|约束条件C/有原承包合同？|
|原合同总面积（亩）|YHTZMJM|Float|15|2|＞0|约束条件C/有原承包合同？|

## ?B.6 `LZHT` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包合同代码a|YCBHTBM|Char|19||非空|M|
|流转合同代码|LZHTBM|Char|18||非空|M|
|承包方代码|CFBBM|Char|18||非空|M|
|受让方代码b|SRFBM|Char|18||非空|M|
|流转方式|LZFS|Char|3||见表C.10|M|
|流转期限|LZQX|Char|10||非空|M|
|流转期限开始日期|LZQXKSRQ|Date|8||YYYYMMDD|M|
|流转期限结束日期|LZQXJSRQ|Date|8||YYYYMMDD|M|
|流转面积|LZMJ|Float|15|2|＞0|M|
|流转地块数|LZDKS|Int|2||＞0|M|
|流转前土地用途|LZQTDYT|Char|1||见表C.9|O|
|流转后土地用途|LZHTDYT|Char|1||见表C.9|O|
|流转费用说明c|LZJGSM|Char|100||非空|M|
|合同签订日期|HTQDRQ|Date|8||YYYYMMDD|M|
|流转面积（亩）|LZMJM|Float|15|2|>0|O|

## ?B.7 `QSLYZLFJ` ????????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|资料附件编号|ZLFJBH|Char|20||非空|M|
|资料附件名称|ZLFJMC|Char|100||非空|M|
|资料附件日期|ZLFJRQ|Date|8||YYYYMMDD|M|
|附件a|FJ|Varbin|||非空|M|

## ?B.8 `CBJYQZDJB` ?????????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|发包方代码|FBFBM|Char|14||非空|M|
|承包方代码|CBFBM|Char|18||非空|M|
|承包方式|CBFS|Char|3||见表C.10|M|
|承包期限|CBQX|Char|30||非空|M|
|承包期限起|CBQXQ|Date|8||YYYYMMDD|M|
|承包期限止a|CBQXZ|Date|8||YYYYMMDD|M|
|地块示意图b|DKSYT|Varbin|254||非空|M|
|承包经营权证流水号|CBJYQZLSH|Char|50||非空|M|
|登记簿附记|DJBFJ|Char|50||非空|O|
|原承包经营权证编号|YCBJYQZLSH|Char|50||非空|O|
|登簿人|DBR|Char|50||非空|M|
|登记时间|DJSJ|DATE|8||非空|M|

## ?B.9 `CBJYQZ` ??????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|发证机关|FZJG|Char|50||非空|M|
|发证日期|FZRQ|Date|8||YYYYMMDD|M|
|权证是否领取|QZSFLY|Char|1||见表C.19|M|
|权证领取日期|QZLQRQ|Date|8||YYYYMMDD|C|
|权证领取人姓名|QZLQRXM|Char|50||非空|C|
|权证领取人证件类型|QZLQRZJLX|Char|1||见表C.15|C|
|权证领取人证件号码|QZLQRZJHM|Char|20||非空|C|

## ?B.10 `CBJYQZ_QZBF` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|权证补发原因|QZBFYY|Char|200||非空|M|
|补发日期|BFRQ|Date|8||YYYYMMDD|M|
|权证补发领取日期|QZBFLQRQ|Date|8||YYYYMMDD|M|
|权证补发领取人姓名|QZBFLQRXM|Char|50||非空|M|
|权证补发领取人证件类型|BFLQRZJLX|Char|1||见表C.15|M|
|权证补发领取人证件号码|BFLQRZJHM|Char|20||非空|M|

## ?B.11 `CBJYQZ_QZHF` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|权证换发原因|QZHFYY|Char|200||非空|M|
|换发日期|HFRQ|Date|8||YYYYMMDD|M|
|权证换发领取日期|QZHFLQRQ|Date|8||YYYYMMDD|M|
|权证换发领取人姓名|QZHFLQRXM|Char|50||非空|M|
|权证换发领取人证件类型|HFLQRZJLX|Char|1||见表C.15|M|
|权证换发领取人证件号码|HFLQRZJHM|Char|20||非空|M|

## ?B.12 `CBJYQZ_QZZX` ????

|????|????|????|????|????|??/??|????|
|---|---|---|---|---|---|---|
|承包经营权证(登记簿)代码|CBJYQZBM|Char|19||非空|M|
|注销原因|ZXYY|Char|200||非空|M|
|注销日期|ZXRQ|Date|8||YYYYMMDD|M|
