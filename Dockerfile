FROM python:3.7.5

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY vzbx-sync.py ./
COPY entrypoint.sh ./

CMD [ "/app/entrypoint.sh" ]