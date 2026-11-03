# -*- coding: utf-8 -*-
"""验证 geoserver_service.get_seed_task_status：提交种子任务并轮询状态解析。"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\Work\RurallandContractExtension\backend")

from app.services.geoserver_service import geoserver_service

LAYER = "erlunyanbao:survey_dk_result"

status0 = geoserver_service.get_seed_task_status(LAYER)
print("idle:", status0)
assert status0["running"] is False, "空闲时应为 running=False"

geoserver_service.seed_tile_cache(
    LAYER,
    grid_set_id="EPSG:4326",
    zoom_start=0,
    zoom_stop=7,
    mime_format="image/png",
    seed_type="reseed",
    thread_count=2,
)
print("submitted, polling...")
seen_running = False
for i in range(40):
    time.sleep(1)
    st = geoserver_service.get_seed_task_status(LAYER)
    if st["running"]:
        seen_running = True
        print(f"t={i+1}s running={st['running']} progress={st['progress']}% done={st['tilesDone']}/{st['tilesTotal']} tasks={len(st['tasks'])}")
    elif seen_running:
        print(f"t={i+1}s finished")
        break
    # 未见过 running 且还没超 40 拍就继续等（任务可能排队）
else:
    print("warning: never observed running state (may have finished between polls)")

final = geoserver_service.get_seed_task_status(LAYER)
print("final:", final)
assert final["running"] is False
assert 0 <= status0["progress"] <= 100
print("PASS")
