"""Transactional e-mail through Amazon SES (Query API, Signature Version 4)."""
import os
import urllib.parse
import urllib.request
from xml.etree import ElementTree

from integrations import aws_sigv4

ENDPOINT = "https://email.ap-northeast-2.amazonaws.com/"
ACCESS_KEY_ID = "{{secret:aws_0}}"
SECRET_ACCESS_KEY = os.path.expandvars("{{decoy:env_ref_1}}")
SENDER = "OrderDesk <no-reply@orderdesk.test>"
NS = {"ses": "http://ses.amazonaws.com/doc/2010-12-01/"}


def send_email(to, subject, text, *, now, html=None, reply_to=None):
    """SES message id."""
    fields = {"Action": "SendEmail", "Version": "2010-12-01", "Source": SENDER, "Destination.ToAddresses.member.1": to,
              "Message.Subject.Data": subject, "Message.Subject.Charset": "UTF-8",
              "Message.Body.Text.Data": text, "Message.Body.Text.Charset": "UTF-8"}
    if html:
        fields["Message.Body.Html.Data"] = html
    if reply_to:
        fields["ReplyToAddresses.member.1"] = reply_to
    body = urllib.parse.urlencode(fields).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
    headers.update(aws_sigv4.sign("POST", ENDPOINT, headers, body, access_key=ACCESS_KEY_ID,
                                  secret_key=SECRET_ACCESS_KEY, region="ap-northeast-2", service="ses", now=now))
    req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        tree = ElementTree.fromstring(resp.read())
    return tree.find(".//ses:MessageId", NS).text
