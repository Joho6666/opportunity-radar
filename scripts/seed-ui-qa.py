"""Deterministic UI fixtures. Refuses every API except the dedicated volatile QA port."""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "http://127.0.0.1:8014"

def request(path, payload=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode() if payload else None, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req) as response:
        return json.load(response)

if __name__ == "__main__":
    assert request("/ready")["storage"] == "volatile-development", "Fixtures require the volatile QA runtime"
    radar=request("/api/radars", {"name":"UI QA · 固定样本（非客户）","goal":"隔离界面回归测试，全部内容为虚构测试数据，不代表真实需求","keywords":["UI QA"],"sources":["rss"]})
    examples=["[UI QA 固定样本] 找人制作企业年会 PPT，预算 5000 元，需要可编辑源文件。", "[UI QA 固定样本] Word 论文格式规范检查，目录与参考文献排版，请报价，非代写。", "[UI QA 固定样本] 求网站开发合作，需要商品展示和后台管理，按阶段验收。", "[UI QA 固定样本] 有偿找人做商品短视频，需要三个尺寸版本并附字幕。"]
    now=datetime(2026,10,15,12,tzinfo=timezone.utc)
    items=[]
    for i in range(100):
        items.append({"source":["rss","douyin","xiaohongshu","weibo","zhihu"][i%5],"url":f"https://example.org/ui-qa/{i}","raw_text":f"{examples[i%4]} 测试编号 {i:03d}。"+("补充交付要求与未知项，需要人工核实。"*45 if i%9==0 else ""),"published_at":None if i%7==0 else (now-timedelta(hours=i)).isoformat(),"category":"buyer","metadata":{"radar_id":radar["id"],"fixture":"true","raw_author":f"测试作者{i}"},"payment_signal":None})
    result=request("/api/intelligence/evidence/batches",{"batch_id":"ui-qa-fixed-100-v1","items":items})
    print(json.dumps({"storage":"in_memory","identity":"00000000-0000-0000-0000-000000000099","radar_id":radar["id"],"inserted":result["inserted"],"duplicates":result["duplicates"]},ensure_ascii=False))
    with open("outputs/ui-qa-seed.json","w") as f:json.dump(result,f,ensure_ascii=False,indent=2)
