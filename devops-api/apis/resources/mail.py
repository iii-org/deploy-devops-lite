import smtplib
from email.mime.text import MIMEText
from resources import apiError
from resources import logger
from model import db, SystemParameter
import config


class Mail:
    def __init__(self):
        self.__get_account_and_password()
        self.__init_mail_server()

    def __get_account_and_password(self):
        (
            self.smtp_server,
            self.smtp_server_port,
            self.smtp_server_account,
            self.smtp_server_password,
            self.smtp_emission_address,
        ) = get_basic_mail_info()

    @staticmethod
    def check_mail_server(domain=None, port=None, account=None, password=None, emission_email_address=None):
        if domain is None and port is None and account is None and password is None and emission_email_address is None:
            (
                domain,
                port,
                account,
                password,
                emission_email_address,
            ) = get_basic_mail_info()

        server = None

        try:
            server = smtplib.SMTP(domain, port, timeout=3)
        except Exception as e:
            logger.logger.exception(str(e))
            raise apiError.DevOpsError(
                404,
                "Connection refused, port or server are incorrect.",
                error=apiError.login_email_error(),
            )
        server.starttls()

        if account is not None and password is not None:
            try:
                server.login(account, password)
            except smtplib.SMTPAuthenticationError as err:
                logger.logger.exception(str(err))
                if domain.endswith("gmail.com"):
                    raise apiError.DevOpsError(
                        404,
                        "Account needs to apply apppassord to login.",
                        error=apiError.gmail_need_apply_apppassword(account),
                    )
                raise apiError.DevOpsError(404, "SMTP auth error", error=apiError.login_email_error())
            except Exception as e:
                logger.logger.exception(str(e))
                raise apiError.DevOpsError(
                    404,
                    "Account or password are incorrect",
                    error=apiError.login_email_error(),
                )

        return server

    def __init_mail_server(self):
        try:
            self.server = self.check_mail_server()
        except:
            self.server = None

    def send_email(self, receiver, title, message):
        domain = (
            config.get("DEPLOYMENT_NAME")
            if config.get("DEPLOYMENT_NAME") is not None
            else config.get("DEPLOYER_NODE_IP")
        )

        text = MIMEText(message, "plain", "utf-8")
        text["Subject"] = f"[{domain}] {title}"
        text["From"] = self.smtp_emission_address
        text["To"] = receiver
        text["Disposition-Notification-To"] = self.smtp_emission_address

        if self.server is not None:
            logger.logger.info(f"Sending Mail to {receiver}, title: {title}")
            self.server.sendmail(self.smtp_emission_address, receiver, text.as_string())
            logger.logger.info(f"Sending mail done.")
            self.server.quit()


def get_basic_mail_info():
    from resources.redmine import get_mail_config
    from resources.redmine import redmine as redmine_obj

    mail_config = get_mail_config().get("smtp_settings", {})

    smtp_server = mail_config.get("address")
    smtp_server_port = mail_config.get("port")
    smtp_server_account = mail_config.get("user_name")
    smtp_server_password = mail_config.get("password")
    smtp_emission_address = redmine_obj.rm_get_or_set_emission_email_address(None).get("message")
    return (
        smtp_server,
        smtp_server_port,
        smtp_server_account,
        smtp_server_password,
        smtp_emission_address,
    )


def mail_server_is_open():
    mail_config = SystemParameter.query.filter_by(name="mail_config").first()
    return mail_config is not None and mail_config.active
