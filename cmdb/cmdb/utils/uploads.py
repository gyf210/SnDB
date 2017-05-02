# coding=utf-8

from flask import current_app


def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_IMAGE_EXTENSIONS']


def allowed_csv_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['csv']
