import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import io
import pandahouse

import telegram

from pandahouse.core import to_clickhouse, read_clickhouse
from airflow.decorators import dag, task
from datetime import datetime, timedelta




connect = {'host':'https://clickhouse.lab.karpov.courses',
           'password':'dpo_python_2020',
           'user':'student',
           'database':'simulator_20240120'}


# dau, likes, views, ctr (yesterday total values)
query = '''select toDate(time) day, 
                  uniqExact(user_id) dau,
                  countIf(action='like') likes,
                  countIf(action='view') views,
                  round(countIf(action='like') *100/ countIf(action='view'), 2) ctr
           from simulator_20240120.feed_actions
           where toDate(time) = toDate(now()) - 1
           group by day'''
yesterday = pandahouse.read_clickhouse(query=query, connection=connect)


# dau, likes, views, ctr over 7 prev. days
query = '''select toDate(time) day, 
                  uniqExact(user_id) dau,
                  countIf(action='like') likes,
                  countIf(action='view') views,
                  round(countIf(action='like') *100/ countIf(action='view'), 2) ctr
           from simulator_20240120.feed_actions
           where toDate(time) >= toDate(now()) - 7 and toDate(time) <= toDate(now()) - 1
           group by day'''
week = pandahouse.read_clickhouse(query=query, connection=connect)





def daily_report(chat=None):
    chat_id = chat or '-938659451'
    
    # telegram chat connection
    bot = telegram.Bot(token='6621125072:AAEsSuTjyZuCT08xK_9INVwgEJh3K8esVzY')

    # send message
    date = str(yesterday['day'][0]).split(' ')[0]
    dau = yesterday['dau'][0]
    likes = yesterday['likes'][0]
    views = yesterday['views'][0]
    ctr = yesterday['ctr'][0]

    dau_f = f'{dau:_}'.replace('_', ' ')
    likes_f = f'{likes:_}'.replace('_', ' ')
    views_f = f'{views:_}'.replace('_', ' ')

    msg = f'''
    Date {date}

    DAU: {dau_f}
    Likes: {likes_f}
    Views: {views_f}
    CTR: {ctr} % '''
    bot.sendMessage(chat_id=chat_id, text=msg)

    
    # send plot (picture)
    fig, ax = plt.subplots(2,2,figsize=(20,10))
    sns.lineplot(x='day', y='dau', data=week, ax=ax[0][0])
    sns.lineplot(x='day', y='likes', data=week, ax=ax[0][1])
    sns.lineplot(x='day', y='views', data=week, ax=ax[1][0])
    sns.lineplot(x='day', y='ctr', data=week, ax=ax[1][1])
    ax[0][0].set_title('DAU')
    ax[0][1].set_title('Likes')
    ax[1][0].set_title('Views')
    ax[1][1].set_title('CTR')
    ax[0][0].set(xlabel='', ylabel='')
    ax[0][1].set(xlabel='', ylabel='')
    ax[1][0].set(xlabel='', ylabel='')
    ax[1][1].set(xlabel='', ylabel='')
    fig.suptitle('Weekly dashboard')


    # save plots to clipboard
    plot_object = io.BytesIO()
    plt.savefig(plot_object)
    plot_object.seek(0)
    plot_object.name = 'Weekly_dashboard.png'
    plt.close()
    bot.sendPhoto(chat_id=chat_id, photo=plot_object)



default_args = {'owner': 'y.savashevich',
                'depends_on_past': False,
                'retries': 2,
                'retry_delay': timedelta(minutes=10),
                'start_date': datetime(2024, 2, 10)}    


# интервал запуска ДАГа
schedule_interval = '0 11 * * *'                         # start dag every day at 11 a.m.

@dag(default_args=default_args, 
     schedule_interval=schedule_interval, 
     catchup=False)

def get_dag():
    @task
    def make_report():
        daily_report()
        
    make_report()
    
DAG_al_daily_sav = get_dag()