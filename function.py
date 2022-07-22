import urllib,urllib.request,urllib.error,urllib.parse
import json
import datetime
import hmac
import hashlib
import base64
import time
import random
import string
import psycopg2

#🍌データベース関数
def DBSQL(URL:str, SQL, resData:bool=False):
    """
    データベースSQL送信/データ取得
    -----
    URL: データベースURL\n
    SQL: SQLリクエスト文->str/str:list/str:tuple*末尾の;不要!\n
    resData: データ取得有無 bool\n
    return -> 取得データ | 無し
    """
    with psycopg2.connect(URL) as conn:
        with conn.cursor() as cur:
            #リクエストが文字列なら
            if type(SQL) is str:
                cur = conn.cursor()
                cur.execute(SQL)
                if resData:
                    data = cur.fetchall()
            elif type(SQL) is list or tuple:
                data = []
                for aSQL in SQL:
                    cur = conn.cursor()
                    cur.execute(aSQL)
                    if resData:
                        data.append(cur.fetchall())
        
        if resData:
            return data
        else:
            conn.commit()
            return

#🍌データ取得関数
#httpデータ取得関数定義
def getHttpRes(url:str):
    #レスポンスをrawDataに代入
    return urllib.request.urlopen(url)

#httpデータ取得&json変換関数定義
def getHttpJson(url:str):
    #レスポンスrawDataをjson戻す
    return json.load(getHttpRes(url))

#🍌YouTubeAPI関数
#再生リストデータ取得関数定義>戻り値Json>引数名前指定>pageTokenは任意
def getPlData(part:str, plIds:str, apiKey:str, pageToken:str=''):
    #YouTube Data API v3 PlaylistItems:list
    #リクエストURL
    reqUrl = 'https://www.googleapis.com/youtube/v3/playlistItems'
    #最大取得データ数/最大50
    maxResults = '50'
    
    #PageTokenが指定されていたらptToUrlに代入値を代入
    if pageToken == '':
        ptToUrl = ''
    else:
        ptToUrl = '&pageToken='+pageToken

    #GET送信先URL
    url = reqUrl+'?key='+apiKey+'&part='+part+'&playlistId='+plIds+'&maxResults='+maxResults+ptToUrl
    #urlから取得して返す
    print(url)
    return getHttpJson(url)

#動画データ取得関数定義>戻り値Json>引数名前指定>pageTokenは任意
def getVideoData(part:str, videoIds:str, apiKey:str, pageToken:str=''):
    #YouTube Data API v3 Videos:list
    #リクエストURL
    reqUrl = 'https://www.googleapis.com/youtube/v3/videos'
    #最大取得データ数
    maxResults = '50'

    #PageTokenが指定されていたらptToUrlに代入値を代入
    if pageToken == '':
        ptToUrl = ''
    else:
        ptToUrl = '&pageToken='+pageToken

    #GET送信先URL
    url = reqUrl+'?key='+apiKey+'&part='+part+'&id='+videoIds+'&maxResults='+maxResults+ptToUrl
    #urlから取得して返す
    return getHttpJson(url)

#現在の時刻を指定された書式で返す
def getNowTime(dateFormat:str='%Y-%m-%d %H:%M:%S.%f-JST'):
    #時刻取得(GMT+9時間)
    now = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=9))
        )
    #文字列変換&書式設定書式参照->https://docs.python.org/ja/3/library/datetime.html#strftime-and-strptime-behavior)
    strTime = now.strftime(dateFormat)
    return strTime

def ytTimeConbour(YTime:str):
    #YouTUbeから渡される文字列をGMTとしてtimeデータに変換
    timeD = datetime.datetime.strptime(YTime+'+0000', '%Y-%m-%dT%H:%M:%SZ%z')
    #timeデータを日本時間に変換
    jpnTime = timeD.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    #文字列形成
    #分を0埋めで取得
    minuteTime = jpnTime.strftime('%M')
    #任意の書式で文字列出力&返す
    return f'{jpnTime.month}月{jpnTime.day}日 {jpnTime.hour}時{minuteTime}分'

def ytTimeConbourForTitle(YTime:str):
    #YouTUbeから渡される文字列をGMTとしてtimeデータに変換
    timeD = datetime.datetime.strptime(YTime+'+0000', '%Y-%m-%dT%H:%M:%SZ%z')
    #timeデータを日本時間に変換
    jpnTime = timeD.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    #文字列形成
    #分を0埋めで取得
    minuteTime = jpnTime.strftime('%M')
    #現在時刻(日)取得
    now = getNowTime(dateFormat='%d')
    #開始時刻が0分なら
    if minuteTime == '00':
        rtnData = f'{jpnTime.hour}時'
    #30分なら
    elif minuteTime == '30':
        rtnData = f'{jpnTime.hour}時半'
    #それ以外なら
    else:
        rtnData = f'{jpnTime.hour}時{minuteTime}分'
    #深夜(0時から4時)であれば
    if jpnTime.hour <= 4:
        rtnData = '深夜' + rtnData
    #10時までであれば
    elif jpnTime.hour <= 10:
        rtnData = '朝' + rtnData
    #当日でなければ
    if int(now) != jpnTime.day:
        rtnData = f'{jpnTime.day}日' + rtnData
    return rtnData

#🍌Twitter関数
def signaturer(key:str, val:str):
    key = bytes(key, 'UTF-8')
    val = bytes(val, 'UTF-8')
    sign = hmac.new(key, val, hashlib.sha1)
    sign = sign.digest()
    sign = base64.b64encode(sign)
    return str(sign, 'UTF-8')

def urlRequest(url:str, method:str, pram, header:dict):
    """
    リクエスト送信関数
    ---------------
        url: 送信先URL
        method: リクエストメソッド 'GET' or 'POST'
        pram: パラメータ辞書配列
        header: ヘッダー辞書配列
    """

    #methodを大文字に変換
    method = method.upper()
    pram = pram.encode()

    #メソッド分岐
    if method == 'POST':
        #POSTなら何もしない
        pass
    if method == 'GET':
        #GETならURLに?とpramsを追記
        url += '?' + pram
        #urlに追記したのでpramsを消去
        pram = None

    #リクエスト送信
    #エラー対策
    try:
        req = urllib.request.Request(url=url, data=pram, headers=header, method=method)
        
        #リクエスト送信
        res = urllib.request.urlopen(req)
        cont = json.loads(res.read().decode('utf-8'))
        #応答を返す
        return cont

    #エラー時は
    except urllib.error.HTTPError as e:
        #エラーを表示
        print(e.code)
        print(e.reason)
        print(e.headers)
        return 'HTTPREQUESTERROR'

def sendTweet(cK:str, cS:str, aT:str, aTS:str, pram:dict, url='https://api.twitter.com/2/tweets', method='POST'):

    """
    ツイートを送信
    パラメータ
    --------
    cK: consumerKey\n
    cS: consumerSecret\n
    aT: accessToken\n
    aTS: accessTokenSecret\n
    pram: パラメータ群辞書配列\n
    url: エンドポイントURL(デフォ:'.../2/tweets')\n
    method: リクエストメソッド(デフォ:'POST')\n
    """
    #パラメータ文字列変換
    encPram = pram.copy()
    for k, v in encPram.items():
        k = urllib.parse.quote(k, '')
        v = urllib.parse.quote(v, '')
        encPram[k] = str(v)
    
    basePram = {
        'oauth_consumer_key': cK,
        'oauth_token': aT,
        'oauth_nonce': ''.join(random.choices(string.ascii_letters + string.digits, k=11)),
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_version': '1.0',
        'oauth_timestamp': str(int(time.time()))
    }

    #署名作成
    #暗号化する文字列
    signBase = basePram.copy()
    
    #a-z並び替え(sorted())
    signSortKey = sorted(signBase)

    #文字列変換
    method = method.upper()
    signVal = ''
    for key in signSortKey:
        qkey = key
        qval = signBase[key]
        if signVal != '':
            signVal += '&'
        signVal += f'{qkey}={qval}'
    
    encUrl = urllib.parse.quote(url, '')
    signVal = urllib.parse.quote(signVal, '')
    signStr = f'{method}&{encUrl}&{signVal}'
    

    #暗号化に使う鍵
    encConsSec = urllib.parse.quote(cS, '')
    encAccTokSec = urllib.parse.quote(aTS, '')
    signKey = f'{encConsSec}&{encAccTokSec}'

    #暗号化
    signature = signaturer(key=signKey, val=signStr)

    #ヘッダー生成
    headerBace = dict(basePram)
    #ヘッダーに暗号化した文字列を追加
    headerBace.update({'oauth_signature':signature})
    #a-z並び替え
    headerSortKey = sorted(headerBace)

    #文字列変換
    header = {}
    headerStr = ''
    for key in headerSortKey:
        qkey = urllib.parse.quote(key,'')
        qval = urllib.parse.quote(headerBace[key],'')
        if headerStr != '':
            headerStr += ','
        headerStr += f'{qkey}="{qval}"'
    headerStr = f'OAuth {headerStr}'

    header['Authorization'] = headerStr
    header['Content-type'] = 'application/json'
    pramj = json.dumps(pram, ensure_ascii=False)

    return urlRequest(url=url, method=method, pram=pramj, header=header)


#🍌Discord関数
def sendDiscord(webhookUrl:str, text:str):
    url = webhookUrl

    #POSTヘッダー
    headers = {
        'User-Agent': '',
        'Content-Type': 'application/json'
    }
    #送信データ組み立て
    data = {
        'content': text
    }
    #送信データJSON化
    data = json.dumps(data).encode()

    req = urllib.request.Request(url, headers=headers, method='POST', data=data)
    urllib.request.urlopen(req)
