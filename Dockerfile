# base image
FROM python:3.7

# The enviroment variable ensures that the python output is set straight
# to the terminal with out buffering it first
ENV PYTHONUNBUFFERED 1

# RUN pip install --upgra/de pip

# install psycopg2 dependencies
# RUN apk update \
#     && apk add --virtual build-deps gcc python3-dev musl-dev \
#     && apk add postgresql \
#     && apk add postgresql-dev \
#     && pip install psycopg2 \
#     && apk add jpeg-dev zlib-dev libjpeg \
#     && pip install Pillow \
#     && apk del build-deps


WORKDIR /app
COPY ./requirements.txt requirements.txt 
# COPY requirements.txt /moogtmeda/
RUN pip install -r requirements.txt
COPY . .
# RUN python manage.py migrate


