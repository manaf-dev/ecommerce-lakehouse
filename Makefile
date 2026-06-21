.PHONY: install lint format typecheck test smoke build-utils-zip verify-zip clean upload-data tf-validate tf-plan

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/ --cov=src --cov-fail-under=80

smoke:
	pytest tests/unit/test_utils_imports.py -v --no-cov

build-utils-zip:
	python -c "import shutil, pathlib; pathlib.Path('dist').mkdir(exist_ok=True); shutil.make_archive('dist/utils', 'zip', 'src', 'utils')"

verify-zip:
	python -c "import zipfile,sys; z=zipfile.ZipFile('dist/utils.zip'); names=z.namelist(); assert any(n.startswith('utils/') for n in names), f'utils/ root missing from zip: {names}'; print('OK')"

clean:
	python scripts/clean.py

upload-data:
	python scripts/upload_sample_data.py

tf-validate:
	terraform -chdir=terraform/main init -backend=false -input=false
	terraform -chdir=terraform/main validate

tf-plan:
	terraform -chdir=terraform/main plan
