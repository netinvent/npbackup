import sys
import libvirt
import defusedxml.lxml
from npbackup.kvm.exceptions import (
    CubeLibVirtConnectionError,
    CubeLibVirtGetDomByIdError,
    CubeLibVirtGetDomByNameError,
)

# from npbackup.core.runner import write_logs


class DomainHandler:
    """
    Domain handling class

    """

    def __init__(
        self,
        connection_uri: str = None,
        user: str = None,
        password: str = None,
        ro: bool = True,
    ):
        """

        :param connection_uri: (str)
            See https://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html/libvirt_application_development_guide_using_python-Connections-Remote_URIs.html
            driver[+transport]://[username@][hostname][:port]/[path][?extraparameters]

        :param user:
        :param password:
        :param ro:
        :return:
        """
        self.cnx = None
        self.user = user
        self.password = password
        try:
            if ro:
                self.cnx = libvirt.openReadOnly(connection_uri)
            elif user is not None:
                flags = [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE]
                auth = [flags, self.__libvirt_auth_credentials_callback, None]
                self.cnx = libvirt.openAuth(connection_uri, auth, 0)
            else:
                self.cnx = libvirt.open(connection_uri)
        except libvirt.libVirtError as exc:
            raise CubeLibVirtConnectionError

    def __libvirt_auth_credentials_callback(self, credentials, user_data):
        for credential in credentials:
            if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                credential[4] = self.user
                if len(credential[4]) == 0:
                    credential[4] = credential[3]
            elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                credential[4] = self.password
            else:
                return -1
        return 0

    def list_domains_by_name(self):
        try:
            domains = []
            domain_ids = self.cnx.listDomainsID()
            if domain_ids is not None:
                for id in domain_ids:
                    try:
                        name = self.get_dom_by_id(id)
                        domains.append({"name": name, "active": True})
                    except libvirt.libVirtError as exc:
                        print(exc)

            # Defined domains are shutdown and don't have a domainID
            domain_names = self.cnx.listDefinedDomains()
            if domain_names is not None:
                inactive_domains = [
                    {"name": name, "active": False}
                    for name in domain_names
                    if domain_names is not None
                ]

            # TODO: merge inactive and active domains, exclude already existing ones

            return domains
        except libvirt.libVirtError as exc:
            print("yokel")

    def get_dom_by_id(self, id: str):
        try:
            return self.cnx.lookupByID(id)
        except libvirt.libVirtError as exc:
            raise CubeLibVirtGetDomByIdError

    def get_dom_by_name(self, name: str):
        try:
            return self.cnx.lookupByName(name)
        except libvirt.libVirtError as exc:
            raise CubeLibVirtGetDomByNameError

    def external_snapshot(self, dom):
        pass


def get_disks(dom):
    xml = defusedxml.lxml.fromstring(dom.XMLDesc())
    disks = []
    for entry in xml.xpath("devices/disk"):
        disk = {}
        if entry.get("device", None) != "disk":
            continue
        disk["dev"] = entry.xpath("target")[0].get("dev")
        disk["src"] = entry.xpath("source")[0].get("file")
        disk["type"] = entry.xpath("driver")[0].get("type")
        disks.append(disk)

    return disks
