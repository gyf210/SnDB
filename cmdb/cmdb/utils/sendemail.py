# coding=utf-8

from flask import render_template
from flask_mail import Message
from celery.utils.log import get_task_logger
from .. import mail, celery

logger = get_task_logger(__name__)


@celery.task
def send_async_email(sender, to, subject, template, **kwargs):
        msg = Message(subject=subject, sender=sender,  recipients=[to])
        msg.body = render_template(template + '.txt', **kwargs)
        msg.html = render_template(template + '.html', **kwargs)
        logger.info('send message "%s" to %s', msg, to)
        mail.send(msg)

