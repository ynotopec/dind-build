FROM alpine:3.19
RUN echo "Hello from DinD on K8s!" > /tmp/hello.txt
CMD ["cat", "/tmp/hello.txt"]
