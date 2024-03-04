import pandas as pd
import pandahouse
from datetime import datetime, timedelta
from pandahouse.core import to_clickhouse, read_clickhouse
from airflow.decorators import dag, task


# get data from clickhouse
def ch_get_df(query='Select 1'):
    
    connect = {'host':'https://clickhouse.lab.karpov.courses', 
               'password':'dpo_python_2020', 
               'user':'student', 
               'database':'simulator_20240120'}
    df = pandahouse.read_clickhouse(query=query, connection=connect)
    return df


# default settings for full DAG
default_args = {'owner': 'y.savashevich',
                'depends_on_past': False,
                'retries': 2,
                'retry_delay': timedelta(minutes=10),
                'start_date' : datetime(2024, 2, 10)}

schedule_interval = '00 04 * * *'                         # start dag every day at 4 a.m.


# create DAG
@dag(default_args=default_args, 
     schedule_interval=schedule_interval, 
     catchup=False)
def create_dag():
    
    @task()
    def extract_feed():
        query = '''select toDate(time) event_date, user_id, 
                          count(action='view') views,
                          count(action='like') likes
                    from simulator_20240120.feed_actions
                    where toDate(time) = toDate(now()) - 1
                    group by event_date, user_id
                    order by event_date, user_id'''
        feed_t = ch_get_df(query=query)
        return feed_t
    
    @task()
    def extract_mess():
        query = '''select t1.event_date as event_date, user_id, messages_received, messages_sent, users_sent, users_received
                    from
                        (select toDate(time) as event_date, 
                               user_id,
                               count(receiver_id) as messages_sent,
                               uniqExact(receiver_id) as users_sent
                        from simulator_20240120.message_actions
                        where toDate(time) = toDate(now()) - 1
                        group by event_date, user_id
                        order by event_date, user_id) t1
                    join
                        (select toDate(time) as event_date, 
                               receiver_id,
                               count(user_id) as messages_received,
                               uniqExact(user_id) as users_received
                        from simulator_20240120.message_actions
                        where toDate(time) = toDate(now()) - 1
                        group by event_date, receiver_id) t2
                    on t1.event_date = t2.event_date and t1.user_id = t2.receiver_id'''
        mess_t = ch_get_df(query=query)
        return mess_t
    
    @task()
    def extract_user_info():
        query = '''select distinct user_id, gender, age, os
                    from
                        (select distinct user_id, gender, age, os
                        from simulator_20240120.message_actions
                        where toDate(time) = toDate(now()) - 1

                        union all

                        select distinct user_id, gender, age, os
                        from simulator_20240120.feed_actions
                        where toDate(time) = toDate(now()) - 1)'''
        user_info = ch_get_df(query=query)
        return user_info
    
    @task()
    def joining(feed_t, mess_t, user_info):
        feed_mess_df = pd.merge(feed_t, mess_t, on=['event_date', 'user_id'], how='outer')
        full_df = pd.merge(feed_mess_df, user_info, on='user_id', how='outer')

        return full_df
    
    @task()
    def dimension_gender(full_df):
        dimension_val_g = full_df.groupby(['event_date','gender'])['views', 'likes', 
                                                                   'messages_received', 'messages_sent', 
                                                                   'users_received', 'users_sent'].sum().reset_index()
        
        dimension_val_g = dimension_val_g.rename(columns={'gender':'dimension_value'})
        dimension_val_g['dimension'] = 'gender'
        dimension_val_g.insert(1, 'dimension', dimension_val_g.pop('dimension'))
        
        return dimension_val_g

    @task()
    def dimension_age(full_df):
        dimension_val_a = full_df.groupby(['event_date','age'])['views', 'likes', 
                                                                'messages_received', 'messages_sent', 
                                                                'users_received', 'users_sent'].sum().reset_index()
        
        dimension_val_a = dimension_val_a.rename(columns={'age':'dimension_value'})
        dimension_val_a['dimension'] = 'age'
        dimension_val_a.insert(1, 'dimension', dimension_val_a.pop('dimension'))
        
        return dimension_val_a
 
    @task()
    def dimension_os(full_df):
        dimension_val_o = full_df.groupby(['event_date','os'])['views', 'likes', 
                                                               'messages_received', 'messages_sent', 
                                                               'users_received', 'users_sent'].sum().reset_index()
        
        dimension_val_o = dimension_val_o.rename(columns={'os':'dimension_value'})
        dimension_val_o['dimension'] = 'os'
        dimension_val_o.insert(1, 'dimension', dimension_val_o.pop('dimension'))
        
        return dimension_val_o       
           
    @task()
    def transform_to_df(dimension_val_g, dimension_val_a, dimension_val_o):
        final_df = pd.concat([dimension_val_g, dimension_val_a, dimension_val_o])
        final_df = final_df.astype({'dimension':'object', 'dimension_value':'object',
                                    'views':'int', 'likes':'int',
                                    'messages_received':'int', 'messages_sent':'int',
                                    'users_received':'int', 'users_sent':'int'})
        return final_df

    
    # load data into new table to clickhouse
    @task()
    def load_to_table(final_df):
        connect = {'host': 'https://clickhouse.lab.karpov.courses',
                   'database':'test',
                   'user':'student-rw', 
                   'password':'656e2b0c9c'}
    
        pandahouse.to_clickhouse(df=final_df, table="y_savashevich", index=False, connection=connect)
        
    # dag stages one by one
    df1 = extract_feed()
    df2 = extract_mess()
    df3 = extract_user_info()
    join_df1 = joining(df1, df2, df3)
    dem_1 = dimension_gender(join_df1)
    dem_2 = dimension_age(join_df1)
    dem_3 = dimension_os(join_df1)
    join_df2 = transform_to_df(dem_1, dem_2, dem_3)
    load_to_table(join_df2)
        
        
# execution
DAG_y_sav = create_dag()