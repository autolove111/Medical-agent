ARG CONDA_BASE_IMAGE=continuumio/miniconda3:24.11.1-0
FROM ${CONDA_BASE_IMAGE}

ARG CONDA_ENV_NAME=medlab-ocr

ENV CONDA_ENV_NAME=${CONDA_ENV_NAME} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/conda/envs/${CONDA_ENV_NAME}/bin:/opt/conda/bin:$PATH

WORKDIR /tmp/conda-build

COPY environment.yml ./

RUN conda env create -f environment.yml && \
    conda clean -afy

WORKDIR /app

COPY . .

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/v1/health').read()" || exit 1

EXPOSE 8001
CMD ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8001"]
