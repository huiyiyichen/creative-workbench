"""本地模拟飞书开放接口（联调用）：CW_FEISHU_API_BASE=http://127.0.0.1:9911/open-apis。记录存在内存，GET /_records 查看。"""
from fastapi import FastAPI, Request

app = FastAPI()
RECORDS: dict[str, dict] = {}
COLUMNS = [{"field_name": n, "type": t} for n, t in [("标题", 1), ("链接", 15), ("平台", 3), ("发布时间", 5), ("原始指标", 1), ("结论与理由", 1), ("追踪词", 4), ("状态", 3), ("工作台链接", 15)]]

@app.post("/open-apis/auth/v3/tenant_access_token/internal")
async def token(req: Request):
    b = await req.json()
    if b.get("app_secret") != "local-secret":
        return {"code": 10014, "msg": "app secret invalid"}
    return {"code": 0, "tenant_access_token": "t-local", "expire": 7200}

@app.get("/open-apis/bitable/v1/apps/{app}/tables/{table}/fields")
async def fields(app: str, table: str):
    return {"code": 0, "data": {"items": COLUMNS, "has_more": False}}

@app.post("/open-apis/bitable/v1/apps/{app}/tables/{table}/records")
async def create(app: str, table: str, req: Request):
    rid = f"rec{len(RECORDS) + 1}"
    RECORDS[rid] = (await req.json())["fields"]
    return {"code": 0, "data": {"record": {"record_id": rid}}}

@app.put("/open-apis/bitable/v1/apps/{app}/tables/{table}/records/{rid}")
async def update(app: str, table: str, rid: str, req: Request):
    RECORDS[rid].update((await req.json())["fields"])
    return {"code": 0, "data": {"record": {"record_id": rid}}}

@app.get("/_records")
async def records():
    return RECORDS
