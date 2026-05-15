ARG CONDA_BASE_IMAGE=continuumio/miniconda3:24.11.1-0
FROM ${CONDA_BASE_IMAGE}

ARG CONDA_ENV_NAME=medlab-langchain

ENV CONDA_ENV_NAME=${CONDA_ENV_NAME} \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/conda/envs/${CONDA_ENV_NAME}/bin:/opt/conda/bin:$PATH

WORKDIR /tmp/conda-build

COPY environment.yml ./
COPY torch-2.11.0-cp311-cp311-manylinux_2_28_x86_64.whl ./

RUN conda env create -f environment.yml && \
    conda clean -afy

WORKDIR /app

RUN mkdir -p /app/medical_docs /app/vector_db

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
