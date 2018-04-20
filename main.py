# -*- coding: utf-8 -*-
# @Date    : 2016/9/9
# @Author  : hrwhisper
import codecs
import re
import os
import multiprocessing
from multiprocessing.dummy import Pool
from datetime import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from LoginUCAS import LoginUCAS


class UCASCourse(object):
    def __init__(self, time_out=5):
        self.__BEAUTIFULSOUPPARSE = 'html5lib'  # or use 'lxml'
        self.semester = None
        self.save_base_path, self.semester = UCASCourse._read_info_from_file()
        self.session = None
        self.headers = None
        self._init_session()
        self.course_list = []
        self.to_download = []
        self.lock = multiprocessing.Lock()
        self._time_out = time_out

    def _init_session(self):
        t = LoginUCAS().login_sep()
        self.session = t.session
        self.headers = t.headers

    @classmethod
    def _read_info_from_file(cls):
        with codecs.open(r'./private.txt', "r", "utf-8") as f:
            save_base_path = semester = None
            for i, line in enumerate(f):
                if i < 2: continue
                if i == 2:
                    save_base_path = line.strip()
                if i == 3:
                    semester = line.strip()
        return save_base_path, semester

    def _get_course_list(self):
        # 从sep中获取Identity Key来登录课程系统，并获取课程信息
        url = "http://sep.ucas.ac.cn/portal/site/16/801"
        r = self.session.get(url, headers=self.headers)
        code = re.findall(r'"http://course.ucas.ac.cn/portal/plogin\?Identity=(.*)"', r.text)[0]

        url = "http://course.ucas.ac.cn/portal/plogin?Identity=" + code
        self.headers['Host'] = "course.ucas.ac.cn"
        html = self.session.get(url, headers=self.headers).text
        dom_list = BeautifulSoup(html, self.__BEAUTIFULSOUPPARSE).find_all('div', class_='fav-title')
        for item in dom_list:
            if self.semester in item.find('a')['title']: # 只下载本学期课程
                id = item.find('a')['href'].split('/')[-1]
                self.course_list.append([item.find('a')['title'],id])
        return html


    def _get_all_resource_url(self):
        # 从课程的所有URL中获取对应的所有课件
        print('读取课件中......')
        list(map(self._get_resource_url, self.course_list))

    def _get_resource_url(self, base_url, _path=''):
        base_url = 'http://course.ucas.ac.cn/access/content/group/'
        source_name = course_item[0]
        html = self.session.get(base_url+course_item[1], headers=self.headers).text
        tds = BeautifulSoup(html, self.__BEAUTIFULSOUPPARSE).find_all('li')
        res = set()
        for td in tds:
            url = td.find('a')
            if not url: continue
            url = urllib.parse.unquote(url['href'])
            if url == '../': continue
            if 'Folder' in td.text:  # directory
                self._get_resource_url(base_url + url, _path + '/' + url)
            if url.startswith('http:__'):  # Fix can't download when given a web link. eg: 计算机算法分析与设计
                try:
                    res.add((self.session.get(base_url + url, headers=self.headers, timeout=self._time_out).url, _path))
                except requests.exceptions.ReadTimeout:
                    print("Error-----------: ", base_url + url, "添加进下载路径失败,服务器长时间无响应")
                except requests.exceptions.ConnectionError as e:
                    print("Error-----------: ", base_url + url, "添加进下载路径失败,服务器长时间无响应")
            else:
                res.add((base_url + url, _path))

        for url, _path in res:
            self.to_download.append((source_name, _path, url))

    def _start_download(self):
        # 多线程下载
        p = Pool()
        p.map(self._download_file, self.to_download)
        p.close()
        p.join()

    def _download_file(self, param):
        # 下载文件
        dic_name, sub_directory, url = param
        save_path = self.save_base_path + '/' + dic_name + '/' + sub_directory
        with self.lock:
            if not os.path.exists(save_path):  # To create directory
                os.makedirs(save_path)

        filename = url.split('/')[-1]
        save_path += '/' + filename
        if not os.path.exists(save_path):  # To prevent download exists files
            try:
                r = self.session.get(url, stream=True, timeout=self._time_out)
            except requests.exceptions.ReadTimeout as e:
                print('Error-----------文件下载失败,服务器长时间无响应: ', save_path)
            except requests.exceptions.ConnectionError as e:
                print('Error-----------文件下载失败,服务器长时间无响应: ', save_path)

            size_mb = int(r.headers.get('Content-Length')) / (1024 ** 2)
            try:
                print('Start download {dic_name}  >> {sub_directory}{filename}  {size_mb:.2f}MB'.format(**locals()))
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                            f.flush()
                print('{dic_name}  >> {sub_directory}{filename}   Download success'.format(**locals()))
            except UnicodeEncodeError:
                print('{dic_name}  >> {sub_directory} Download a file'.format(**locals()))

    def start(self):
        self._get_course_list()
        self._get_all_resource_url()
        self._start_download()


if __name__ == '__main__':
    start = datetime.now()
    s = UCASCourse()
    s.start()
    print('Task complete, total time:', datetime.now() - start)
    os.system("pause")
