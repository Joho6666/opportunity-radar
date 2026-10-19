import pytest
from app.core.config import validate_runtime
from test_local_edition_contracts import _local_settings


def test_restart_generator_persists_only_explicit_tikhub(tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    script = (root / 'scripts/local.sh').read_text().split("load_private_config() {", 1)[1].split("<<'PY'", 1)[1].split('\nPY', 1)[0]
    folder = tmp_path / 'config'; folder.mkdir()
    cfg = folder / 'local.env'
    required = 'LOCAL_DATABASE_URL=postgresql+psycopg://postgres:fixture@127.0.0.1:5432/test\nLOCAL_REDIS_URL=redis://127.0.0.1:6379/0\nLOCAL_DB_PASSWORD=fixture\nLOCAL_USER_ID=00000000-0000-0000-0000-000000000001\nLOCAL_PROXY_TOKEN=' + 'a'*64 + '\nLOCAL_SESSION_SECRET=' + 'b'*64 + '\n'
    cfg.write_text(required + 'LOCAL_MANUAL_TIKHUB_ENABLED=true\nTIKHUB_API_KEY=test-only\nPAID_DAILY_COST_LIMIT=1\nPAID_DAILY_REQUEST_LIMIT=20\nLLM_API_KEY=must-not-copy\nFIRECRAWL_API_KEY=must-not-copy\n')
    env = dict(os.environ)
    command = [sys.executable, '-c', script, str(cfg), str(folder/'local-runtime.env'), str(root), str(tmp_path), sys.executable, '/usr/bin/true']
    from dotenv import dotenv_values
    for _ in range(2):
        subprocess.run(command, env=env, check=True, capture_output=True)
        from dotenv import dotenv_values
        result = dotenv_values(folder/'local-runtime.env')
        assert result['PAID_API_ENABLED'] == 'true'
        assert result['TIKHUB_API_KEY'] == 'test-only'
        assert result['LLM_API_KEY'] == result['FIRECRAWL_API_KEY'] == ''
        assert result['ENABLE_AI_CLASSIFICATION'] == 'false'
        assert result['AUTH_DISABLED'] == 'false'
        assert result['LOCAL_PRIVATE_CONFIG_DIR'] == str(folder)  # 界面内 Provider 密钥/预算的私密目录
    cfg.write_text(required + 'TIKHUB_API_KEY=test-only\n')
    subprocess.run(command, env=env, check=True, capture_output=True)
    result = dotenv_values(folder/'local-runtime.env')
    assert result['PAID_API_ENABLED'] == 'false' and result['TIKHUB_API_KEY'] == ''


def test_explicit_local_manual_tikhub_is_allowed(monkeypatch):
    monkeypatch.setenv('INCLUDE_MOCK_COLLECTOR', 'false')
    monkeypatch.setattr('app.core.config.get_settings', lambda: _local_settings(
        paid_api_enabled=True, local_manual_tikhub_enabled=True, tikhub_api_key='test-only'))
    validate_runtime()


def test_local_manual_gate_rejects_other_providers_and_scheduled(monkeypatch):
    from app.services.billing_gateway import reserve, paid_context
    from app.core.errors import AppError
    settings = _local_settings(paid_api_enabled=True, local_manual_tikhub_enabled=True, tikhub_api_key='test-only')
    monkeypatch.setattr('app.services.billing_gateway.get_settings', lambda: settings)
    with paid_context(object(), 'test', 'test', 'test', scheduled=True):
        with pytest.raises(AppError, match='手动'):
            reserve('tikhub', 'xiaohongshu')
    with pytest.raises(AppError, match='TikHub'):
        reserve('llm', 'llm')


def test_run_readback_preserves_collection_filter_stats():
    from datetime import datetime, UTC
    from app.repositories.postgres import PostgresRepository
    row = dict(id='11111111-1111-4111-8111-111111111111', radar_id='22222222-2222-4222-8222-222222222222', status='completed',
               query_count=1, items_found=20, items_deduplicated=0, items_analyzed=15, opportunities_found=0, matched_count=0, recommended_count=0,
               error_message=None, error_code=None, started_at=datetime.now(UTC), finished_at=datetime.now(UTC), heartbeat_at=None,
               stage_stats={'collection_filtered': {'stale': 5}, 'collected': 20})
    result = PostgresRepository._run_from_row(object.__new__(PostgresRepository), row)
    assert result.stage_stats['collection_filtered']['stale'] == 5


def test_source_readiness_needs_exact_quote_not_just_key(monkeypatch):
    from app.collectors.tikhub_catalog import source_catalog
    settings = _local_settings(paid_api_enabled=True, local_manual_tikhub_enabled=True, tikhub_api_key='test-only')
    monkeypatch.setattr('app.services.price_evidence.verified_tikhub_price', lambda endpoint: (0.01, {}) if endpoint == '/api/v1/xiaohongshu/app_v2/search_notes' else None)
    items = {i['id']: i for i in source_catalog(settings)}
    assert items['xiaohongshu']['available'] is True
    assert items['xiaohongshu']['status'] == '可运行 · 已实测'
    assert items['xiaohongshu']['live_verified'] is True  # 真实付费响应证据已记录
    assert items['zhihu']['available'] is False
    assert items['zhihu']['status'] == '已配置 · 未实测'  # 无精确报价时阻止收费
    assert items['linkedin']['status'] == '已配置 · 价格未核验'
    assert items['web_search']['available'] is False
