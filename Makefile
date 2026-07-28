.PHONY: backend-install backend-test backend-run frontend-install frontend-build frontend-run verify-audit

backend-install:
	cd backend && pip install -e ".[dev]" --break-system-packages

backend-test:
	cd backend && pytest -q

backend-run:
	cd backend && uvicorn app.main:app --reload

frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

frontend-run:
	cd frontend && npm run dev

verify-audit:
	cd backend && python3 scripts/verify_audit_chain.py --all
