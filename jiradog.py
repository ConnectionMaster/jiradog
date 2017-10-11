#!/usr/bin/python

import sys
import requests
import json
import io
import urllib
import re
from datadog import initialize, api
from pprint import pprint
import time
from jira import JIRA
import logging

class jira_provider(object):
  """This creates the paginated URLS (multiple urls to hit because the total results exceed the maximum allowable returned results) and calls the API, returning results.

  Args:
      provider_config:	Dictionary, the part of the config that defines the data provider source, and JQL query string.
      project:		String, the JIRA project that will be put into the templatized JQL query string.
      max_results:	Integer, currently hard set at 100, maximum supported by JIRA.
      username:		String, the username of the user who is being used to access the API over basic HTTP auth.
      password:		String, password of the above user.
      server:		String, JIRA server url instance; where to hit the API.

  Returns:
      A list of dictionaries that are the JSON objects returned by the API calls. All URLS are generated by the paginate function.
  """
  def __init__(self, username, password, server):
    """Create JIRA object. This function is currently not used because we haven't switched to using the JIRA python SDK yet.

    Args:
        username:	String, the username of the user who is being used to access the API over basic HTTP auth.
        password:	String, password of the above user.
        server:		String, JIRA server url instance; where to hit the API.

    Returns:
        A single JIRA object for SDK use.
    """
    jira = JIRA(server, basic_auth=(username, password))

  def paginate(self, base_api_url, total, max_results):
    """Create a list of JIRA API search urls appended with '&startAt=N' in order to get all results from a JQL query.

    Args:
        base_api_url:	String, the specified API url, given by the provide function, derived from the jql key in the metric config file.
        total:		Integer, total number of issues, pulled from the original API call.
        max_results:	Integer, currently hard set at 100, maximum supported by JIRA.

    Returns:
        A list of urls, with the appended '&startAt=N' that, when looped, will pull all JQL search results.
    """
    paginations = []
    start_at = max_results    
    while (start_at < total):
      paginations.append(base_api_url + '&startAt=' + str(start_at))
      start_at = int(start_at) + int(max_results)
    return paginations

  def provide(self, provider_config, project, max_results):
    """Makes API calls using the JIRA API, version 2, search.

    Args:
        provider_config:	Dictionary, the part of the config that defines the data provider source, and JQL query string.
        project:		String, the JIRA project that will be put into the templatized JQL query string.
        max_results:		Integer, currently hard set at 100, maximum supported by JIRA.

    Returns:
        A list of dictionaries that are the JSON objects returned by the API calls. All URLS are generated by the paginate function.
    """
    jql_raw_regex = re.sub(r"{{project}}", project, provider_config["jql"])
    jql_url_encoded = urllib.quote(jql_raw_regex)
    jira_api_call_url = api_endpoint + jql_url_encoded + '&maxResults=' + max_results
    jira_api_response = json.loads(requests.get(jira_api_call_url, headers=headers, auth=(api_username, api_password)).text)
    jira_api_responses = [jira_api_response]
    for url in self.paginate(jira_api_call_url, jira_api_response['total'], max_results):
      jira_api_response = requests.get(url, headers=headers, auth=(api_username, api_password))
      jira_api_responses.append(json.loads(jira_api_response.text))
    return jira_api_responses

class constant_provider(object):
  """Data provider for data hard-coded in the metric config file.

  Args:
      data:                   Dictionary      Data from the metric config file.
      project:                String          The JIRA project; used to get data from the imported dictionary.
      NULL_max_results:       Integer         NULL metric, to allow generalized usaged. Unused by this function.

  Returns:
      A single value from a hard coded dictionary included the in the metric config file.
  """
  def provide(self, data, project, NULL_max_results):
    """Retrieves and retunrs explicit data hard-coded into the metric config file.

    Args:
        data:			Dictionary	Data from the metric config file.
        project:		String		The JIRA project; used to get data from the imported dictionary.
        NULL_max_results:	Integer		NULL metric, to allow generalized usaged. Unused by this function.

    Returns:
        A single value from a hard coded dictionary included the in the metric config file.	
    """
    return data["data"][project]

def average(numerator, denominator):
  """Finds the average of 2 numbers.

  Args:
      numerator:	Integer		The numerator, found using one of the data providers.
      denominator:	Integer		The denominator, found using one of the data providers.

  Returns:
      Integer of the resulting division. If the denominator is 0, sets the returned value as 0.
  """
  if denominator != 0:
    return float(numerator)/float(denominator)
  else:
    return 0

def mean_time_to_between_statuses(first_date, second_date):
  """Calculates the length of time between two statuses

  Args:
      first_date:	String	A simple string of the start date in the format '%Y-%m-%dT%H:%M:%S'
      second_date:	String	A simple string of the end date in the format '%Y-%m-%dT%H:%M:%S'

  Returns:
      Floating point number in days
  """
  first_date_sec = time.strptime(first_date.split('.')[0],'%Y-%m-%dT%H:%M:%S')
  second_date_sec = time.strptime(second_date.split('.')[0],'%Y-%m-%dT%H:%M:%S')
  return (time.mktime(second_date_sec) - time.mktime(first_date_sec)) / 60 / 60 / 24

def ticket_count(result, null_field):
  """Gets the count of issues from a JQL query result.

  Args:
      result:		List	A single page from an API call.
      null_field:	None	Used to allow automating method type.

  Returns:
      Integer of the number of issues counted.
  """
  return len(result['issues'])

def custom_field_sum(result, custom_field):
  """
  """
  custom_field_values = []
  for issue in result['issues']:
    if issue['fields'][custom_field] is None:
      custom_field_values.append(2)
    else:
      custom_field_values.append(issue['fields'][custom_field])
  return sum(custom_field_values)

def get_number_average(provider_config, position, project):
  """Gets and returns either numerator or denominator for average method from metric config file and data provider

  Args:
      provider_config:	Dictionary	Pulled from the metric config, contains source, and arguments.
      position:		String		Indicates if this is the numerator or denominator
      project:		String		The jira project being injected into the templatized JQL query string.

  Returns:
      A float to act as the numerator.
  """
  if provider_config['source'] == 'jira':
    logging.info('data provider: ' + provider_config['source'])
    paginated_list = jp.provide(provider_config, project, max_results)
    running_total = []
    for result in paginated_list:
      running_total.append(function_map[provider_config['method']](result, provider_config['field']))
    number = sum(running_total)
    logging.info(position + ': ' + str(number))
  elif provider_config['source'] == 'constant':
    logging.info('data provider: ' + provider_config['source'])
    number = cp.provide(provider_config, project, max_results)
    logging.info(position + ': ' + str(number))
  else:
    logging.error('avg_' + position + ' ' + 'data provider is set to an unknown value: ' + provider_config['source'])
    sys.exit(1)
  return number

function_map = {
  'average': average,
  'mean_time_to_between_statuses': mean_time_to_between_statuses,
  'ticket_count': ticket_count,
  'custom_field_sum': custom_field_sum
}
max_results = str(100)
config_file = '/etc/jiradog.conf'
log_prepend = '[INFO]'
headers = {'Content-type': 'application/json'}
upload_payload = {}

with open(config_file) as config_data_file:
  config_data_loaded = json.load(config_data_file)

api_username = config_data_loaded['jira']['username']
api_password = config_data_loaded['jira']['password']
api_url = config_data_loaded['jira']['server']
api_endpoint = api_url + '/rest/api/2/search?jql='
log_file = config_data_loaded['local']['log_file']

# Set logging config
logging_levels = {
  'info': logging.INFO,
  'debug': logging.DEBUG,
  'warning': logging.WARNING,
  'error': logging.ERROR,
  'critical': logging.CRITICAL
  }
logging_level = logging_levels.get('debug', logging.NOTSET)
logging.basicConfig(filename=log_file, format='%(asctime)s %(levelname)s %(message)s', level=logging_level)

logging.info('api configuration set')

initialize(**config_data_loaded['datadog'])
logging.info('initializated datadog SDK')

for metric_file in sys.argv[1:]:
  log_prepend = '[INFO]'

  with open(metric_file) as metric_data_file:
    metric_data_loaded = json.load(metric_data_file)
  logging.info('loaded metric config')

  metric_file_method = metric_data_loaded['method']
  datadog_metric_name = metric_data_loaded['metric_name']

  jp = jira_provider(api_username, api_password, api_url)
  cp = constant_provider()

  timestamp = time.time()
  upload_payload = []

  # JIRA api call
  for project in metric_data_loaded['projects']:
    logging.info('project: ' + project)
    ## Method: Average
    if metric_data_loaded['method'] == 'average':
      logging.info('method: ' + metric_data_loaded['method'])
      avg_numerator = get_number_average(metric_data_loaded['avg_numerator'], 'numerator', project)
      avg_denominator = get_number_average(metric_data_loaded['avg_denominator'], 'denominator', project)
      points = function_map[metric_file_method](avg_numerator, avg_denominator)

    ## Method: mean time between statuses
    if metric_data_loaded['method'] == 'mean_time_to_between_statuses':
      logging.info('method: ' + metric_data_loaded['method'])

      date_diff_days = []
      paginated_list = jp.provide(metric_data_loaded['issues'], project, max_results)
      for status_dates in paginated_list:
        for issue_fields in status_dates['issues']:
          date_diff_days.append(mean_time_to_between_statuses(issue_fields['fields']['created'],issue_fields['fields']['updated']))
      total_time_between_statuses = sum(date_diff_days)
      total_issue_count = paginated_list[0]['total']

      if total_issue_count != 0:
        points = average(total_time_between_statuses, total_issue_count)
      else:
        points = 0

    ## Construct payload for upload
    metric_data = {
      'metric': datadog_metric_name,
      'points': (timestamp, points),
      'tags': ["jira_project:%s" % project]
      }
    upload_payload.append(metric_data) 

  logging.info('payload: ' + str(upload_payload))

  # Upload to DataDog
  result = api.Metric.send(upload_payload)
  logging.info('uploaded to DataDog')
