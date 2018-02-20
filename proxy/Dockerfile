FROM debian
MAINTAINER Olivier Sallou <olivier.sallou@irisa.fr>

RUN apt-get update && apt-get install -y python3-dev python3-pip
RUN pip3 install arrow requests gunicorn flask
RUN mkdir /opt/biocontainers
COPY jenkins_proxy.py /opt/biocontainers/

RUN useradd biocontainers
RUN chown -R biocontainers /opt/biocontainers
USER biocontainers

WORKDIR /opt/biocontainers

EXPOSE 9080

ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:9080", "jenkins_proxy:app"]
