import collections
import pprint
import os
import json
import datetime

import requests
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pylab

_URL_PREFIX = 'https://fhir-open-api.smarthealthit.org'
_CACHE_PATH = '/tmp/patients'
_MINIMUM_COUNT_TO_DISPLAY = 50
_CACHE_ENABLE = True
#_CACHE_ENABLE = False
_DATE_FORMAT = '%Y-%m-%d'

_START_DATE = datetime.date(year=2005, month=1, day=1)
_STOP_DATE = datetime.date(year=2007, month=1, day=1)


class Cache(object):
    def set(self, key, value):
        key_phrase = '/'.join(key)
        filepath = os.path.join(_CACHE_PATH, key_phrase)

        cache_path = os.path.dirname(filepath)
        if os.path.exists(cache_path) is False:
            os.makedirs(cache_path)

        with open(filepath, 'w') as f:
            json.dump(value, f)

    def get(self, key):
        key_phrase = '/'.join(key)
        filepath = os.path.join(_CACHE_PATH, key_phrase)

        try:
            if _CACHE_ENABLE is True:
                with open(filepath, 'r') as f:
                    return json.load(f)
        except IOError:
            pass

        raise KeyError(key_phrase)

def _get_url_for_resource_type(resource_type):
    return _URL_PREFIX + '/' + resource_type

def _get_url_for_resource(name):
    """Expect a name/title like "Observation/844-systolic"."""

    return _URL_PREFIX + '/' + name

def _get_json_data(url, parameters={}):
    headers = {
        'Accept': 'application/json',
    }

    r = requests.get(url, headers=headers, params=parameters)
    r.raise_for_status()

    return r.json()

def do_search(resource_type, metaresource=None, parameters={}):
    url = _get_url_for_resource_type(resource_type)
    if metaresource is not None:
        url += '/' + metaresource

    data = _get_json_data(url, parameters=parameters)
    
    if data['totalResults'] == 0:
        return

    # The "entry" child is actually a list.
    try:
        for entry in data['entry']:
            yield (entry['title'], entry['updated'], entry['content'])
    except KeyError as e:
        print("Missing key [{0}] in the entry data:\n{1}".\
              format(str(e), pprint.pformat(data)))
        raise

def get_vital_signs_for_patient(patient_id):
    c = Cache()
    key = ('vitals', str(patient_id))

    try:
        return c.get(key)
    except KeyError:
        pass

    parameters = {
        'subject:Patient': patient_id,
    }

    rows = do_search('Observation', metaresource='_search', parameters=parameters)

    vitals = [
        (
            content['appliesDateTime'], 
            content['name']['coding'][0], 
            content['valueQuantity']
        ) 
        for (title, update_timestamp, content) 
        in rows 
        if 'valueQuantity' in content
    ]

    c.set(key, vitals)

    return vitals

def get_patients():
    c = Cache()
    key = ('patients', 'list')

    try:
        return c.get(key)
    except KeyError:
        pass

    patient_id_list = []
    for title, update_timestamp, content in do_search('Patient'):
        identifier = content['identifier'][0]
        assert identifier['label'] == 'SMART Hospital MRN', \
               "Identifier type is unexpected."

        patient_id_list.append(int(identifier['value']))

    c.set(key, patient_id_list)

    return patient_id_list

def _plot_histogram(title, data):
    data = np.array(data)

    d = sns.distplot(data, kde=False)
    d.axes.set_title(title)

    plt.show()

    # This fixes an issue with the graph not showing on some types of systems. 
    # show() doesn't exist under Python 3.4, but the issue seems specific to 
    # Python 2.x .
    try:
        method = getattr(pylab, 'show')
    except AttributeError:
        pass
    else:
        method()

def _main():
    vital_bins = collections.defaultdict(list)
    index = {}

    patients = get_patients()
    patients = list(patients)

    minimum_date_found = None
    maximum_date_found = None
    for i, patient_id in enumerate(patients):
        print("Reading patient ({0})/({1}): ({2})".format(i + 1, len(patients), patient_id))

        for date_phrase, coding, value in get_vital_signs_for_patient(patient_id):
            # Sometimes we get an 8601 timestamp, and sometimes it's just a 
            # date. Distill it.
            date_phrase = date_phrase[:10]

            date_dt = datetime.datetime.strptime(date_phrase, _DATE_FORMAT).date()

# TODO(dustin): Technically, we can filter via the original query, but it's not
#               documentated so well. I got sick on monkeying with it.
            if (_START_DATE <= date_dt < _STOP_DATE) is False:
                continue

            if minimum_date_found is None or minimum_date_found > date_dt:
                minimum_date_found = date_dt

            if maximum_date_found is None or maximum_date_found < date_dt:
                maximum_date_found = date_dt

            vital_bins[coding['code']].append(value)
            index[coding['code']] = coding['display']

    print('')
    print("Date range: {0} => {1}".\
          format(minimum_date_found, maximum_date_found))

    print('')

    print("Counts")
    print('')

    # Order by count.
    counts = { k: len(vital_bins[k]) for k in index.keys() }
    sorted_ = sorted(counts.items(), key=lambda x: x[1])

    for vital_code, count in sorted_:
        if count < _MINIMUM_COUNT_TO_DISPLAY:
            continue

        print("[{0}] [{1}]: ({2})".format(index[vital_code], vital_code, count))

        value_dicts = vital_bins[vital_code]
        values = [v['value'] for v in value_dicts]
        
        # Grab the unit-name from the first one.
        unit_name = value_dicts[0]['units']
        _plot_histogram("Community Histogram: {0} ({1})\n{2} to {3}".\
                        format(index[vital_code], unit_name, 
                               minimum_date_found, maximum_date_found), values)

if __name__ == '__main__':
    _main()
