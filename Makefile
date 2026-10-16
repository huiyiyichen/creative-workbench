# =============================================================================
# 创意工作台命令入口
#
#   make setup          安装后端 + 前端依赖
#   make test           跑后端 + 前端测试
#   make lint           ruff + 分层 + 前端类型检查
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help setup test test-backend test-frontend \
        lint lint-backend lint-frontend layering backup

help:  ## 列出所有可用目标
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## 安装后端(dev)与前端依赖
	cd backend && uv sync
	cd frontend && npm ci

test: test-backend test-frontend  ## 跑后端 + 前端测试

test-backend:  ## 后端全量 pytest（DATABASE_URL 指向独立的 creative_workbench_test* 库）
	cd backend && uv run python -m pytest

test-frontend:  ## 前端 vitest + 覆盖率门禁（对应 CI frontend-tests）
	cd frontend && npm run test:coverage

lint: lint-backend layering lint-frontend  ## 完整质量门（ruff + 分层 + tsc）

lint-backend:  ## 后端 ruff 全量检查 + 格式检查（手动质量门）
	cd backend && uv run ruff check . && uv run ruff format --check .

layering:  ## 分层检查：api/v1 经 service / repository 访问数据
	cd backend && uv run python scripts/check_layering.py

lint-frontend:  ## 前端类型检查（AGENTS.md 首选，比 npm run lint 稳）
	cd frontend && npx tsc --noEmit

backup:  ## 备份数据库（PG pg_dump，保留最近 7 份）
	cd backend && ./scripts/backup_db.sh
