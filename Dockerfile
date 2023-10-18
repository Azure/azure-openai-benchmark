FROM python:3.11

WORKDIR /app
ADD benchmark/ benchmark/
ADD requirements.txt .
RUN pip install -r requirements.txt --root-user-action=ignore

ENTRYPOINT [ "python", "-m", "benchmark.bench" ]
