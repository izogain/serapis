#!/usr/bin/env python2
# coding=utf-8
"""
AWS Lambda Handler
"""
from __future__ import unicode_literals
from __future__ import absolute_import

__author__ = "Manuel Ebert"
__copyright__ = "Copyright 2015, summer.ai"
__date__ = "2015-11-09"
__email__ = "manuel@summer.ai"


import json
import sys
sys.path.append('.')

from serapis import tasks
from serapis.config import config
from serapis.preprocess import clean_and_qualify_term
from serapis.util import hashslug, get_source_from_url, now
from serapis.preprocess import qualify_term, clean_sentence

import nltk
nltk.data.path.append("nltk_data/")


tasks_map = {
    "search": tasks.search,
    "detect": tasks.detect,
    "save": tasks.save
}


def run_task(bucket, key):
    task, _, _ = key.split(":")
    contents = config.s3.Object(bucket, key).get()
    message = json.loads(contents['Body'].read())
    tasks_map[task](message)


def add_words(bucket, key):
    contents = config.s3.Object(bucket, key).get()
    words = contents['Body'].read().splitlines()
    added, skipped = set(), []
    for term in words:
        term = clean_and_qualify_term(term)
        if term:
            slug = hashslug(term)
            if slug not in added:
                added.add(slug)
                message = {'word': term, 'hashslug': slug}
                tasks.write_message('search', message)
            else:
                skipped.append(term)
        else:
            skipped.append(term)
    print "Added {} terms, skipped {}".format(len(added), len(skipped))


def handler(event, context):
    if "term" in event:  # API call
        if not qualify_term(event['term']):
            return {'error': 'Invalid search term'}
        message = {
            "word": event['term'],
            'hashslug': hashslug(event['term'])
        }
        if "sentence" in event:  # Detect
            s_clean, variants = clean_sentence(event['sentence'], event['term'])
            message['crawl_date'] = now()
            message['urls'] = [{
                "url": event.get('url'),
                "source": get_source_from_url(event.get('url')),
                "sentences": [{
                    "s": event['sentence'],
                    "s_clean": s_clean,
                }],
                "variants": list(variants)
            }]
            return tasks.detect(message)
        else:  # Search
            return tasks.search(message)

    elif "Records" in event:  # This comes from S3
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            key = key.replace("%3A", ":")  # That's my URLDecode.
            if key.count(":") == 2:
                return run_task(bucket, key)
            elif key.endswith(".wordlist"):
                return add_words(bucket, key)
            else:
                print "Don't know what to do with '{}'".format(key)
