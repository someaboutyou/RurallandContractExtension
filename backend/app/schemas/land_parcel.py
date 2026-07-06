from pydantic import BaseModel


class LandParcelItem(BaseModel):
    dkbm: str
    dkmc: str | None = None
    htmj: str | None = None
    yhtmj: str | None = None
    htmjm: str | None = None
    yhtmjm: str | None = None
    syqxz: str | None = None
    dklb: str | None = None
    dldj: str | None = None
    tdyt: str | None = None
    tdlylx: str | None = None
    sfjbnt: str | None = None
    scmj: str | None = None
    dkdz: str | None = None
    dkxz: str | None = None
    dknz: str | None = None
    dkbz: str | None = None
    dkbzxx: str | None = None
    fbfbm: str | None = None
    fbfmc: str | None = None
    cbjyqqdfs: str | None = None
    cbhtbm: str | None = None
    cbjyqzbm: str | None = None
    lzhtbm: str | None = None
    sfqqqg: str | None = None
    cbfbm: str | None = None
    cbfmc: str | None = None
    cbflx: str | None = None
    resultStatus: str | None = None
    isChanged: bool = False
    changeType: str | None = None
    changeReason: str | None = None
    geometry: dict | None = None
