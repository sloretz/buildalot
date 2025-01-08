FROM ghcr.io/containerd/busybox:1.36

RUN echo "ros-core test success" > /ros-core.txt
ARG FROM
RUN echo "FROM: ${FROM}" > /from.txt

COPY ./ros_entrypoint.sh /
ENTRYPOINT ["/ros_entrypoint.sh"]
