FROM alpine:latest
RUN apk add --no-cache tor
COPY torrc /etc/tor/torrc
RUN mkdir -p /var/lib/tor/hidden_service && chown -R tor:tor /var/lib/tor
USER tor
CMD ["tor", "-f", "/etc/tor/torrc"]
