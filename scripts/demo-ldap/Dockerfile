FROM alpine:3.18

RUN apk add --no-cache openldap openldap-clients openldap-back-mdb

COPY slapd.conf /etc/openldap/slapd.conf
COPY init.ldif /etc/openldap/init.ldif

RUN mkdir -p /var/lib/openldap/openldap-data && \
    mkdir -p /run/openldap && \
    chown -R ldap:ldap /var/lib/openldap /run/openldap /etc/openldap && \
    su -s /bin/sh ldap -c "slapadd -f /etc/openldap/slapd.conf -l /etc/openldap/init.ldif"

EXPOSE 389

CMD ["slapd", "-d", "256", "-u", "ldap", "-g", "ldap", "-h", "ldap:///", "-f", "/etc/openldap/slapd.conf"]