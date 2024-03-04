import pandas as pd
import numpy as np
import scipy.stats as st
import pandahouse
from datetime import datetime, date, timedelta
import telegram
from pandahouse.core import read_clickhouse
from airflow.decorators import dag, task



connect = {'host':'https://clickhouse.lab.karpov.courses',
           'password':'dpo_python_2020',
           'user':'student',
           'database':'simulator_20240120'}


query = '''select toStartOfFifteenMinutes(time) ts,
                   toDate(ts) day,
                   formatDateTime(ts, '%R') hour,
                   uniqExact(user_id) feed_users,
                   countIf(action='view') views,
                   countIf(action='like') likes,
                   round(countIf(action='like')*100/countIf(action='view'),2) ctr
            from simulator_20240120.feed_actions
            where ts >=  today() - 7 and ts < toStartOfFifteenMinutes(now())
            group by ts, day, hour
            order by ts'''
feed = pandahouse.read_clickhouse(query=query, connection=connect)

query = '''select toStartOfFifteenMinutes(time) ts,
               toDate(ts) day,
               formatDateTime(ts, '%R') hour,
               uniqExact(user_id) messanger_users,
               count(receiver_id) messages
        from simulator_20240120.message_actions
        where ts >=  today() - 7 and ts < toStartOfFifteenMinutes(now())
        group by ts, day, hour
        order by ts'''
mess = pandahouse.read_clickhouse(query=query, connection=connect)



# previous days periods method (5 days):
#     feed_users - 00:00 - 11:00 + 1:15, 18:00 - 23:45
#     views - 00:00 - 10:00 + 1:15, 19:00 - 23:45
#     likes - 00:00 - 10:00 + 1:15, 19:00 - 23:45
#     messanger_users - 05:00 - 11:00 + 1:15, 16:00 - 23:45
#     messages - 05:00 - 11:00 + 1:15, 16:00 - 23:45
    
    
# previous 15-min periods method (5 15-min):
#     feed_users - 12:15 - 18:00
#     views - 11:15 - 19:00
#     likes - 11:15 - 19:00
#     ctr - 01:15 - 23:45
#     messanger_users - 12:15 - 16:00
#     messages - 12:15 - 16:00
    


# confidence interval method
def check_anomaly(df, metric):
    current_ts = df['ts'].max()                # the last 15-min
    day = str(current_ts).split(' ')[0]
    hour = str(current_ts).split(' ')[1][:-3]
    
    # if metric has the rapid ascent then we will use previous days periods method
    if metric == 'feed_users' and ((hour >= '00:00' and hour <= '12:15') or (hour >= '18:00' and hour <= '23:45')):
        ago_value_list = []
        for n in range(1,4):
            day_ago_ts = current_ts - pd.DateOffset(days=n)
            metric_value = df[df['ts'] == day_ago_ts][metric].values[0]
            ago_value_list.append(metric_value)
     
    elif (metric == 'views' or metric == 'likes') and ((hour >= '00:00' and hour <= '11:15') or (hour >= '19:00' and hour <= '23:45')):
        ago_value_list = []
        for n in range(1,6):
            day_ago_ts = current_ts - pd.DateOffset(days=n)
            metric_value = df[df['ts'] == day_ago_ts][metric].values[0]
            ago_value_list.append(metric_value)
        
    elif metric == 'ctr' and (hour >= '00:00' and hour <= '01:15') or (hour >= '20:00' and hour <= '23:45'):
        ago_value_list = []
        for n in range(1,6):
            day_ago_ts = current_ts - pd.DateOffset(days=n)
            metric_value = df[df['ts'] == day_ago_ts][metric].values[0]
            ago_value_list.append(metric_value)
    
    elif (metric == 'messanger_users' or metric == 'messages') and ((hour >= '00:00' and hour <= '10:15') or (hour >= '20:00' and hour <= '23:45')):
        ago_value_list = []
        for n in range(1,6):
            day_ago_ts = current_ts - pd.DateOffset(days=n)
            metric_value = df[df['ts'] == day_ago_ts][metric].values[0]
            ago_value_list.append(metric_value)  
          
    # if metric has the plateau then we will use previous 15-min periods method
    else:
        period = -5
        ago_value_list = df[metric].values[period-1:-1]

    # count confidence interval
    st_int = st.t.interval(alpha=0.95, 
                           df=len(ago_value_list)-1, 
                           loc=np.mean(ago_value_list), 
                           scale=st.sem(ago_value_list))

    # anomaly check
    current_value = df[df['ts'] == current_ts][metric].iloc[0]
    high = st_int[1]
    low = st_int[0]   

    if current_value > high:
        is_alert = True
        abs_diff = abs(current_value - high)
    elif current_value < low:
        is_alert = True
        abs_diff = abs(current_value - low)
    else:
        is_alert = False
        abs_diff = 0

    return day, hour, high, low, current_value, is_alert, abs_diff


# reporting
def alert_sending(df, metric, limit):
    day = check_anomaly(df, metric)[0]
    hour = check_anomaly(df, metric)[1]
    high = round(check_anomaly(df, metric)[2], 2)
    low = round(check_anomaly(df, metric)[3], 2)
    current_value = check_anomaly(df, metric)[4]
    is_alert = check_anomaly(df, metric)[5]
    abs_diff = check_anomaly(df, metric)[6]

    if is_alert==True:
        if current_value > high and abs_diff > limit:
            diff = round(abs_diff*100 / high, 2)
            count = 1
            msg = f'''Data {day}, time {hour} \n
Have anomaly: the current value {current_value} of metric {metric} is over {diff} % higher then limit {high}'''

        elif current_value < low and abs_diff > limit:
            diff = round(abs_diff*100 / low, 2)
            count = 1
            msg = f'''Дата {day}, время {hour} \n
Have anomaly: the current value {current_value} of metric {metric} is over {diff} % lower then limit {low}'''
                
        else:
            count = 0
            msg = ''
    else:
        count = 0
        msg = ''

    return count, msg
    




# create dag
def alerts_finding(chat=None):
    chat_id = chat or '-938659451'
    
    # telegram bot connection
    bot = telegram.Bot(token='6621125072:AAEsSuTjyZuCT08xK_9INVwgEJh3K8esVzY')
    
    # anomality check
    alerts = []
    msgs = []
    board = 'Metrics dashboard link: https://superset.lab.karpov.courses/superset/dashboard/5096/' 
    
    # Feed
    f_metrics = feed.columns[3:].tolist()
    for metric in list(f_metrics):

        # absolute limit
        if metric == 'feed_users':
            limit = 50
        elif metric == 'views':
            limit = 1000
        elif metric == 'likes':
            limit = 150
        else:
            limit = 1.3
        
        alrt = alert_sending(feed, metric, limit)[0]
        msg = alert_sending(feed, metric, limit)[1]
        if len(msg) > 1:
            alerts.append(alrt)
            msgs.append(msg)
        else:
            continue
            
    # Messenger
    m_metrics = mess.columns[3:].tolist()
    for metric in list(m_metrics):

        # absolute limit
        if metric == 'messanger_users':
            limit = 25
        else:
            limit = 35
            
        alrt = alert_sending(mess, metric, limit)[0]  
        msg = alert_sending(mess, metric, limit)[1]
        if len(msg) > 1:
            alerts.append(alrt)
            msgs.append(msg)
        else:
            continue

    if sum(alerts) > 0:   
        for i in msgs:
            bot.sendMessage(chat_id=chat_id, text=i)
        bot.sendMessage(chat_id=chat_id, text=board)
        
        

default_args = {'owner': 'y.savashevich',
                'depends_on_past': False,
                'retries': 2,
                'retry_delay': timedelta(minutes=1),
                'start_date': datetime(2024, 2, 24)} 

schedule_interval = '*/15 * * * *'                        # start every 15 minutes

@dag(default_args=default_args, 
     schedule_interval=schedule_interval,
     catchup=False)
def find_alert_every_15_min():
    @task
    def make_report():
        alerts_finding()
    make_report()
    
DAG_alerts_sav = find_alert_every_15_min()