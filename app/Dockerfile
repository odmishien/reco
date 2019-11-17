FROM python:3.6

WORKDIR /app
RUN mkdir log audio_logs

COPY Pipfile Pipfile.lock ./

RUN pip install -U pip && pip install pipenv && pipenv install --system
