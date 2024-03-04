import pandas as pd
import io
import pandahouse

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

import telegram

# to dag creation
from pandahouse.core import read_clickhouse
from airflow.decorators import dag, task
from datetime import datetime, timedelta




# datatime format transformation for plots
def timestamp_do_date(df_column):
    dates = []
    for i in df_column:
        i = str(i).split(' ')[0]
        dates.append(i)
    return dates


# get data from clickhouse
def ch_get_df(query='Select 1'):
    connect = {'host':'https://clickhouse.lab.karpov.courses', 
               'password':'dpo_python_2020', 
               'user':'student', 
               'database':'simulator_20240120'}
    df = pandahouse.read_clickhouse(query=query, connection=connect)
    return df


default_args = {'owner': 'y.savashevich',
                'depends_on_past': False,
                'retries': 2,
                'retry_delay': timedelta(minutes=10),
                'start_date': datetime(2024, 2, 18)}    

schedule_interval = '0 11 * * *'                         # start dag every day at 11 a.m.



def daily_report(chat=None):
    chat_id = chat or '-938659451'
    
    # telegram chat bot connection
    bot = telegram.Bot(token='6621125072:AAEsSuTjyZuCT08xK_9INVwgEJh3K8esVzY')

    # load weekly data
    query = '''select day, uniqExact(user_id) users, 
                       sum(messages) total_messages,
                       sumIf(messages, source='ads') ads_messages, sumIf(messages, source='organic') organic_messages,
                       countIf(distinct user_id, source='ads') ads_users, countIf(distinct user_id, source='organic') organic_users,
                       countIf(distinct user_id, user_type='new' and source='ads') ads_new_users, 
                       countIf(distinct user_id, user_type='new' and source='organic') organic_new_users,
                       min(median_session_time_min) median_session_time_minute,
                       countIf(user_id, session_time_min > 75_perc_session) over_75p_session
                from
                    (select day, user_id,
                            min(source) source, min(user_type) user_type,
                            sum(messages) messages,
                            sum(session_min_in_hour) session_time_min, 
                            median(session_time_min) over(partition by day) median_session_time_min,
                            quantile(0.75)(session_time_min) over(partition by day) 75_perc_session
                    from
                        (select day, hour, user_id, min(source) source, min(user_type) user_type,
                               count(receiver_id) messages,
                               dateDiff('minute', min(time), max(time)) session_min_in_hour
                        from
                            (select time, day, hour, user_id, source, receiver_id,
                                    if(day=start, 'new', 'old') user_type
                            from
                                (select time, toDate(time) day, toHour(time) hour, 
                                        user_id, source, receiver_id,
                                        min(toDate(time)) over(partition by user_id) start
                                from simulator_20240120.message_actions)
                            where day >= toDate(now()) - 7 and day <= toDate(now()) - 1)
                        group by day, hour, user_id)
                    group by day, user_id)
                group by day'''
    messenger = ch_get_df(query=query)

    query = '''select *
                from
                    (select toDate(time) day, 
                           uniqExact(post_id) posts, 
                           countIf(action='like') likes, 
                           countIf(action='view') views,
                           countIf(distinct post_id, post_type='new') new_posts
                    from
                        (select *, if(toDate(time) = start_day_p, 'new', 'old') post_type
                        from
                            (select time, post_id, action
                            from simulator_20240120.feed_actions
                            where toDate(time) >= toDate(now()) - 7 and toDate(time) <= toDate(now()) - 1) t1
                        join
                            (select post_id, min(toDate(time)) start_day_p
                            from simulator_20240120.feed_actions
                            group by post_id) t2
                        using post_id)
                    group by day
                    having day >= toDate(now()) - 7 and day <= toDate(now()) - 1) posts
                join
                    (select day, 
                              uniqExact(user_id) users,
                               countIf(user_id, source='ads') ads_users, countIf(user_id, source='organic') organic_users, 
                               countIf(user_id, source='ads' and user_type='new') ads_new_users, 
                               countIf(user_id, source='organic' and user_type='new') organic_new_users,
                               sumIf(activity, source='ads') ads_activity, sumIf(activity, source='organic') organic_activity,
                               min(median_session_time_min) median_session_time_minute,
                               countIf(user_id, session_time_min > 75_perc_session) over_75p_session
                        from
                            (select day, user_id, min(source) source, min(user_type) user_type,
                                   sum(activity) activity, sum(session_min_in_hour) session_time_min, 
                                   median(session_time_min) over(partition by day) median_session_time_min,
                                   quantile(0.75)(session_time_min) over(partition by day) 75_perc_session
                            from    
                                (select day, hour, user_id, min(source) source, min(user_type) user_type,
                                       count(action) activity,
                                       dateDiff('minute', min(time), max(time)) session_min_in_hour
                                from
                                    (select time, day, hour, user_id, action, source,
                                            if(day=start, 'new', 'old') user_type
                                    from
                                        (select time, toDate(time) day, toHour(time) hour, 
                                                user_id, action, source,
                                                min(toDate(time)) over(partition by user_id) start
                                        from simulator_20240120.feed_actions)
                                    where day >= toDate(now()) - 7 and day <= toDate(now()) - 1)
                                group by day, hour, user_id)
                            group by day, user_id)
                        group by day) users
                using day'''
    feed = ch_get_df(query=query)

    query = '''select day, uniqExact(user_id) users
                from
                    (select distinct t1.day, user_id
                    from
                        (select distinct toDate(time) day, user_id
                        from simulator_20240120.feed_actions
                        where toDate(time) >= toDate(now()) - 7 and toDate(time) <= toDate(now()) - 1) t1
                    join
                        (select distinct toDate(time) day, user_id
                        from simulator_20240120.message_actions
                        where toDate(time) >= toDate(now()) - 7 and toDate(time) <= toDate(now()) - 1) t2
                    on t1.day=t2.day and t1.user_id=t2.user_id)
                group by day'''
    both = ch_get_df(query=query)

    query = '''select active_days, count(distinct user_id) users_count
                from
                    (select user_id, count(distinct toDate(time)) active_days
                    from simulator_20240120.feed_actions
                    group by user_id
                    union all
                    select user_id, count(distinct toDate(time)) active_days
                    from simulator_20240120.message_actions  
                    group by user_id)
                group by active_days            
                order by users_count'''
    app_retention = ch_get_df(query=query)

    query = '''select *
                from
                    (select hour, uniqExact(user_id) mess_users, count(receiver_id) messages
                    from
                        (select toHour(time) hour, user_id, receiver_id
                        from simulator_20240120.message_actions
                        where toDate(time) <= toDate(now()) - 1)
                    group by hour) t1
                join
                    (select hour, uniqExact(user_id) feed_users, uniqExact(post_id) posts, count(action) feed_clicks
                    from
                        (select toHour(time) hour, user_id, post_id, action
                        from simulator_20240120.feed_actions
                        where toDate(time) <= toDate(now()) - 1)
                    group by hour) t2
                using hour'''
    yesterday_activity = ch_get_df(query=query)
    
    


    # plots creation
 

    # DAU
    app_users = pd.DataFrame()
    app_users['day'] = feed['day']
    app_users['feed'] = feed['users']
    app_users['messenger'] = messenger['users']
    app_users['both'] = both['users']

    colors = ['orange', 'seagreen', 'brown']
    custom_params = {'axes.spines.right': False, 'axes.spines.top': False}

    app_users[['day','feed','messenger','both']].set_index('day').plot(kind='bar', stacked=True, color=colors, alpha=0.5)

    plt.ticklabel_format(useOffset=False, axis='y')
    plt.gca().set_ylabel('')
    plt.gca().set_xlabel('')
    plt.gca().legend(labels=['DAU feed', 'DAU messenger', 'DAU both'], loc='upper right', bbox_to_anchor=(1.5, 1))
    plt.gca().set_xticklabels(labels=timestamp_do_date(app_users['day']), rotation=45, ha='right')
    plt.gca().set_title('Unique users amount amount by last 7 days')

    # save plots to clipboard
    plot_object_1 = io.BytesIO()                                  # new object
    plt.savefig(plot_object_1)                                    # save object
    plot_object_1.seek(0)                                         # coursor to file's start (otherwise we will send nothing)
    plot_object_1.name = 'Weekly_dashboard_1.png'                 # plot's name
    plt.close()                                                   # close clipboard

    

    # User distribution by traffic
    fig,ax = plt.subplots(2,2, figsize=(20,10))

    feed[['day','ads_users', 'organic_users']].set_index('day').plot(kind='bar', stacked=True, color=['orange', 'khaki'], alpha=0.5, ax=ax[0][0])
    feed[['day','ads_new_users','organic_new_users']].set_index('day').plot(kind='bar', stacked=True, color=['orange', 'khaki'], alpha=0.5, ax=ax[0][1])

    ax[0][0].set_xlabel('')
    ax[0][0].set_xticklabels('')
    ax[0][1].set_xlabel('')
    ax[0][1].set_xticklabels('')
    ax[0][0].set_title('Feed's users by traffic source')
    ax[0][1].set_title('Feed's new users by traffic source')
    ads = mpatches.Patch(color='orange', label='advertisement', alpha=0.5)
    org = mpatches.Patch(color='khaki', label='organic', alpha=0.5)
    ax[0][0].legend(handles=[org,ads], loc='upper right')
    ax[0][1].get_legend().remove()

    messenger[['day','ads_users', 'organic_users']].set_index('day').plot(kind='bar', stacked=True, color=['limegreen', 'green'], alpha=0.5, ax=ax[1][0])
    messenger[['day','ads_new_users','organic_new_users']].set_index('day').plot(kind='bar', stacked=True, color=['limegreen', 'green'], alpha=0.5, ax=ax[1][1])

    ax[1][0].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')
    ax[1][1].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')
    ax[1][0].set_xlabel('')
    ax[1][1].set_xlabel('')
    ax[1][0].set_title('Messenger's users by traffic source')
    ax[1][1].set_title('Messenger's new users by traffic source')
    ads = mpatches.Patch(color='limegreen', label='advertisement', alpha=0.5)
    org = mpatches.Patch(color='green', label='organic', alpha=0.5)
    ax[1][0].legend(handles=[org,ads], loc='upper right')
    ax[1][1].get_legend().remove()

    # save plots to clipboard
    plot_object_2 = io.BytesIO()
    plt.savefig(plot_object_2)
    plot_object_2.seek(0)
    plot_object_2.name = 'Weekly_dashboard_2.png'
    plt.close()
    
    

    #Likes, Views, Messanges (activity)
    colors = ['khaki', 'gold', 'forestgreen']
    fig,ax = plt.subplots(1,2, figsize=(10,5))

    sns.barplot(x=feed['day'], y=feed['views'], color=colors[0], ax=ax[0], alpha=0.5)
    sns.barplot(x=feed['day'], y=feed['likes'], color=colors[1], ax=ax[0], alpha=0.5)
    sns.barplot(x=messenger['day'], y=messenger['total_messages'], color=colors[2], ax=ax[0], alpha=0.5)

    ax[0].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')
    ax[0].set_ylabel('')
    ax[0].set_xlabel('')
    ax[0].set_title('Users activity')

    sns.barplot(x=feed['day'], y=(feed['views']/feed['users']), color=colors[0], ax=ax[1], alpha=0.5)
    sns.barplot(x=feed['day'], y=(feed['likes']/feed['users']), color=colors[1], ax=ax[1], alpha=0.5)
    sns.barplot(x=messenger['day'], y=(messenger['total_messages']/messenger['users']), color=colors[2], ax=ax[1], alpha=0.5)

    ax[1].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')
    ax[1].set_ylabel('')
    ax[1].set_xlabel('')
    ax[1].set_title('Average activity per user')

    view = mpatches.Patch(color=colors[0], label='views', alpha=0.5)
    like = mpatches.Patch(color=colors[1], label='likes', alpha=0.5)
    mess = mpatches.Patch(color=colors[2], label='messanges', alpha=0.5)
    plt.legend(handles=[view, like, mess], loc='upper right')
    
    # save plots to clipboard
    plot_object_3 = io.BytesIO()
    plt.savefig(plot_object_3)
    plot_object_3.seek(0)
    plot_object_3.name = 'Weekly_dashboard_3.png'
    plt.close()
    
    

    #Users activity by traffic for feed and messenger
    fig,ax = plt.subplots(1,2, figsize=(15,5))

    feed[['day','ads_activity', 'organic_activity']].set_index('day').plot(kind='bar', stacked=True, color=['orange', 'khaki'], alpha=0.5, ax=ax[0])
    messenger[['day','ads_messages','organic_messages']].set_index('day').plot(kind='bar', stacked=True, color=['limegreen', 'green'], alpha=0.5, ax=ax[1])

    ax[0].set_xlabel('')
    ax[0].set_xticklabels('')
    ax[0].set_title('Feed's users activity by traffic')
    f_ads = mpatches.Patch(color='orange', label='advertisement', alpha=0.5)
    f_org = mpatches.Patch(color='khaki', label='organic', alpha=0.5)
    ax[0].legend(handles=[f_org,f_ads], loc='upper right')
    ax[0].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')

    ax[1].set_xlabel('')
    ax[1].set_xticklabels('')
    ax[1].set_title('Messenger's users activity by traffic')
    m_ads = mpatches.Patch(color='limegreen', label='advertisement', alpha=0.5)
    m_org = mpatches.Patch(color='green', label='organic', alpha=0.5)
    ax[1].legend(handles=[m_org,m_ads], loc='upper right')
    ax[1].set_xticklabels(labels=timestamp_do_date(messenger['day']), rotation=45, ha='right')

    # save plots to clipboard
    plot_object_4 = io.BytesIO()
    plt.savefig(plot_object_4)
    plot_object_4.seek(0)
    plot_object_4.name = 'Weekly_dashboard_4.png'
    plt.close()
    
    

    # Hign activity evaluation for feed and messenger
    fig,ax = plt.subplots(1,2, figsize=(15,5))

    sns.barplot(x=feed['day'], y=feed['over_75p_session']/feed['users'], color='khaki', ax=ax[0], alpha=0.5)
    sns.barplot(x=messenger['day'], y=messenger['over_75p_session']/messenger['users'], color='seagreen', ax=ax[0], alpha=0.5)

    ax[0].set_xlabel('')
    ax[0].set_ylabel('')
    ax[0].set_title('Share of users who use service more that 75 percentile')
    ax[0].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')

    sns.barplot(x=feed['day'], y=feed['median_session_time_minute'], color='khaki', ax=ax[1], alpha=0.5)
    sns.barplot(x=messenger['day'], y=messenger['median_session_time_minute'], color='seagreen', ax=ax[1], alpha=0.5)

    ax[1].set_xlabel('')
    ax[1].set_ylabel('')
    ax[1].set_title('Median session time (minutes)')
    m_f = mpatches.Patch(color='khaki', label='лента', alpha=0.5)
    m_m = mpatches.Patch(color='seagreen', label='мессэнджер', alpha=0.5)
    ax[1].legend(handles=[m_f,m_m], loc='upper right')
    ax[1].set_xticklabels(labels=timestamp_do_date(feed['day']), rotation=45, ha='right')

    # save plots to clipboard
    plot_object_5 = io.BytesIO()
    plt.savefig(plot_object_5)
    plot_object_5.seek(0)
    plot_object_5.name = 'Weekly_dashboard_5.png'
    plt.close()
    
    

    # Posts amount: unique and new
    fig, ax1 = plt.subplots()

    sns.barplot(x=feed['day'],y=feed['posts'], palette=['khaki'], alpha=0.5)
    sns.barplot(x=feed['day'],y=feed['new_posts'], palette=['orange'], alpha=0.5)

    ax1.set_xlabel('')
    ax1.set_ylabel('')
    ax1.set_xticklabels('')
    ax1.set_title('Posts distribution')
    post = mpatches.Patch(color='khaki', label='всего', alpha=0.5)
    new = mpatches.Patch(color='orange', label='новые посты', alpha=0.5)
    ax1.legend(handles=[post,new], loc='upper right')

    # save plots to clipboard
    plot_object_6 = io.BytesIO()
    plt.savefig(plot_object_6)
    plot_object_6.seek(0)
    plot_object_6.name = 'Weekly_dashboard_6.png'
    plt.close()
    
    

    # App's retention
    fig, ax1 = plt.subplots()

    sns.scatterplot(x=app_retention['active_days'],y=app_retention['users_count'])

    ax1.set_ylabel('users amount')
    ax1.set_xlabel('days amount')
    ax1.set_title('App's retention')
    plt.show()
    
    # save plots to clipboard
    plot_object_7 = io.BytesIO()
    plt.savefig(plot_object_7)
    plot_object_7.seek(0)
    plot_object_7.name = 'Weekly_dashboard_7.png'
    plt.close()
    
    

    # Yesterday hourly activity
    fig,ax = plt.subplots(1,2, figsize=(15,5))

    sns.lineplot(x=yesterday_activity['hour'], y=yesterday_activity['feed_clicks'], color='orange', ax=ax[0], alpha=0.5)

    ax[0].set_xlabel('')
    ax[0].set_ylabel('')
    ax[0].set_title('Feed's hourly activity')

    sns.lineplot(x=yesterday_activity['hour'], y=yesterday_activity['messages'], color='limegreen', ax=ax[1], alpha=0.5)

    ax[1].set_xlabel('')
    ax[1].set_ylabel('')
    ax[1].set_title('Messenger's hourly activity')
    
    # save plots to clipboard
    plot_object_8 = io.BytesIO()
    plt.savefig(plot_object_8)
    plot_object_8.seek(0)
    plot_object_8.name = 'Weekly_dashboard_8.png'
    plt.close()
    


    # txt to chat bot
    msg = 'Report for the previous 7 days'
    
    
    # sending
    bot.sendMessage(chat_id=chat_id, text=msg)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_1)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_2)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_3)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_4)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_5)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_6)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_7)
    bot.sendPhoto(chat_id=chat_id, photo=plot_object_8)
    
    

# start dag
@dag(default_args=default_args, 
     schedule_interval=schedule_interval, 
     catchup=False)
def daily_report_dag_sav():
    @task
    def make_report():
        daily_report()
        
    make_report()
    
DAG_daily_report_sav = daily_report_dag_sav()