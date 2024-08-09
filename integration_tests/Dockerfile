FROM bats/bats

RUN apk add --no-cache --update python3 py3-pip R
RUN mkdir -p /root/.config/pip
COPY pip.conf /root/.config/pip/pip.conf
COPY Rprofile /root/.Rprofile
