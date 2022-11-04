include .env
export

TARGET_SYSTEM_PYTHON="/usr/bin/env python3.9"

LOCAL_PYTHON_VERSION = 3.9.12
PYTHON_DIR = $(shell pyenv root)/versions/${LOCAL_PYTHON_VERSION}/bin
SYSTEM_PYTHON = ${PYTHON_DIR}/python3
SYSTEM_PIP = ${PYTHON_DIR}/pip
# virtual environment vars
VENV = $(shell pwd)/venv
PYTHON_VENV = ${VENV}/bin/python3
VENV_PIP = ${VENV}/bin/pip3

# Compile and install python dependencies in virtual environment
venv: reqs/requirements.in
	test -d ${VENV} || ${SYSTEM_PYTHON} -m venv $(VENV)
	${VENV_PIP} install pip-tools
	${VENV}/bin/pip-compile --output-file=requirements.txt reqs/requirements.in
	${VENV_PIP} install --no-cache-dir -r requirements.txt

run:
	${VENV}/bin/gunicorn app.main:app \
		--workers ${WORKERS} \
		--worker-class uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:${APP_PORT}
# Make a python zipapp with Linkedin's shiv tool
zipapp: clean reqs/requirements.in
	${SYSTEM_PIP} install shiv
	${SYSTEM_PIP} install pip-tools
	${PYTHON_DIR}/pip-compile --output-file=requirements.txt reqs/requirements.in
	${SYSTEM_PIP} install . --target=dist/
	${SYSTEM_PIP} install --no-cache-dir -r requirements.txt --target=dist/
	$$(cp .env dist/)
	${PYTHON_DIR}/shiv \
		--site-packages dist \
		--compressed \
		-o ${APP_NAME}.pyz \
		-e app.gunicorn_server:run \
		--preamble shiv_cleanup.py \
		-p ${TARGET_SYSTEM_PYTHON}

run_zipapp: zipapp
	$(shell ./${APP_NAME}.pyz)

clean:
	rm -rf __pycache__
	rm -rf $(VENV)
	rm -rf dist build *.egg-info
	find . -type f -name '*.pyz' -delete

.PHONY: venv run clean
