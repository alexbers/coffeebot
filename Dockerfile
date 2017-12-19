FROM alpine:3.6

RUN adduser coffee -u 10000 -D

RUN apk add --no-cache python3 python3-dev py3-requests
RUN pip3.6 install gunicorn

COPY start.sh coffeeapi.py secrets.py coffeebot.py db /home/coffee/coffeebot/

RUN chown -R coffee:coffee /home/coffee

WORKDIR /home/coffee/coffeebot/
CMD ["./start.sh"]
