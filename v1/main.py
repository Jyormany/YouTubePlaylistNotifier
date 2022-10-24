import datetime
import os
import function as qnly

"""
使用するHerokuPostgreDatabaseテーブル
playlists :検知させる再生リストのIDと情報
  ├- id : TEXT / 変更を検知させる再生リストID <-検知再生リスト追加時はこの項目のみを手入力で追加
  ├- etag : TEXT / 再生リストから最後に取得したEtag
  ├- update : TEXT / 最終変更検知日時+状態
  └- Localplno : INTEGER / 再生リストに付けられたローカルな連番

videoids :非公開等を除く検知した動画と状態
  ├- id : TEXT / Video ID
  ├- getdataat : TEXT / データ取得日時
  ├- tweet : TEXT / ツイート状況
  └- localplno : INTEGER / 検知元の再生リストに付けられたローカルな連番

info :通知に添付する連絡文
  ├- no : SERIAL / 連番 <-自動追加)
  └- text : TEXT / 連絡本文 <-文字数超過でツイートに失敗するとキャンセルされる <-連絡文データはツイート成功時に削除

waiting :指定時間後に通知予定の指定時間中に検知した再生リストの変更リスト
  ├- id : TEXT / Video ID
  └- localplno : INTEGER / 検知元の再生リストに付けられたローカルな連番

"""

#環境変数として読み込む機密情報============================

#YouTube API
YTApiKey = os.environ.get("YOUTUBE_API_KEY")

#Twitter API
#ConsumerKey
cK = os.environ.get("TWITTER_CONSUMER_KEY")
#ConsumerSecret
cS = os.environ.get("TWITTER_CONSUMER_SECRET")
#AccessToken
aT = os.environ.get("TWITTER_ACCESS_TOKEN")
#AccessTokenSecret
aTS = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

#Discord Webhook
dcUrl = os.environ.get("DISCORD_URL")

#Heroku Database URL(変更される可能性あり/Herokuサイト環境変数から読み込む)
HerokuDBUrl = os.environ.get("DATABASE_URL")

#====================================================

#事故対策/ツイート送信回数制限(指定回数を超えるとツイートしない)
tweetLimit = 10

#通知制限時間帯設定(配信開始を除く通知を停止/止めている間の通知は設定時間帯後に送信される/日付は跨げない/日本時間)
#通知停止時刻(24時間表記のx時台)
notifyStopTime = 1
#通知開始時刻(24時間表記のx時台)
notifyStartTime = 6

#現在時刻取得(日本時間)
nowTimeHour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).hour
#通知制限時間帯であれば
if notifyStopTime <= nowTimeHour <= notifyStartTime:
  stopNotify = True
else:
  stopNotify = False

#新しいvideoIdを取得する

#更新検知対象の再生リストID取得
plIdsData = qnly.DBSQL(HerokuDBUrl, 'SELECT * FROM playlists', True)
#IDのみリスト化
plIds = []
for plIdData in plIdsData:
  plIds.append(plIdData[0])

#過去に検知済のvideoID取得
videoIdsData = qnly.DBSQL(HerokuDBUrl, 'SELECT * FROM videoids', True)
#辞書配列化
viIdHis = {}
for viIdData in videoIdsData:
  hisId = viIdData[0]
  viIdHis[hisId] = {'localPlNo':viIdData[1]}

#通知停止時間帯中に検知したvideoId取得
waitingVideoIdsData = qnly.DBSQL(HerokuDBUrl, 'SELECT * FROM waiting', True)
#IDのみリスト化
waitingVideoIds = []
for waitingVideoId in waitingVideoIdsData:
  waitingVideoIds.append(waitingVideoId[0])

#変数定義
newViId = [] #新規追加予定リスト
taskVideoIds = {} #変更を検知したvideoID辞書配列
changedPls = [] #変更を検知した再生リストIDリスト配列
recordTask = {} #履歴追記タスク辞書配列

#再生リストの数繰り返し
for plIdData in plIdsData:
  #ID取り出し
  plId = plIdData[0]
  #Etag取り出し
  oldEtag = plIdData[1]
  #localPlNo取り出し
  loPlNo = plIdData[3]

  #pageToken初期値設定
  pageToken = ''
  pageTokenGet = True

  #同一再生リスト取得回数初期化
  plLoad = 0

  #pageTokenが取得できなくなるまで繰り返し
  while pageTokenGet == True:

    #データ取得
    #取得データパラメーター
    part = 'contentDetails,status'
    #関数getPlDataから再生リストデータ取得してresDataに代入
    resData = qnly.getPlData(part=part, plIds=plId, apiKey=YTApiKey, pageToken=pageToken)
    #取得回数カウント
    plLoad += 1

    #pageTokenループ1回目なら
    if plLoad == 1:
      #記録時刻取得
      time = qnly.getNowTime()
      #etag取得
      nowEtag = resData['etag']
      #この再生リストのデータは初取得か？
      if oldEtag == None or '':
        newPl = True
        #ローカル再生リストNo生成
        loPlNo = plIds.index(plId)
        #データベース更新
        qnly.DBSQL(HerokuDBUrl, f"UPDATE playlists SET etag='{nowEtag}', update='NewId<={time}', localplno={loPlNo} WHERE id='{plId}'")
      
      else:
        newPl = False
        #もしlocalPlNoのデータがなかったら
        if loPlNo == None or '':
          #localPlNo生成
          loPlNo = plIds.index(plId)
          #データベース更新
          qnly.DBSQL(HerokuDBUrl, f"UPDATE playlists SET localplno={loPlNo} WHERE id='{plId}'")
          
        #Etag変更検知
        if oldEtag != nowEtag:
          #データベース更新
          qnly.DBSQL(HerokuDBUrl, f"UPDATE playlists SET etag='{nowEtag}', update='{time}' WHERE id='{plId}'")
          #Discord変更通知対象追記
          changedPls.append(plId)

    #videoIdの数だけ繰り返し
    for item in resData['items']:
      #videoIdを取得
      vI = item['contentDetails']['videoId']
      #privasyStatus取得(公開設定)
      pS = item['status']['privacyStatus']
      #公開設定の判別/'private'(非公開)または'privacyStatusUnspecified'(削除済)ではなく、履歴と取得済みIDに記録がなければ
      if pS != 'private' and pS != 'privacyStatusUnspecified' and (vI in viIdHis) == False and (vI in newViId) == False:
        #履歴追記
        #現在時刻取得
        time = qnly.getNowTime()

        #取得済みデータ追記
        newViId.append(vI)

        #通知対象であれば
        if not newPl:
          #通知タスクに追記
          taskVideoIds[vI] = {'localPlNo':loPlNo, 'waiting':False}

        else:
          #履歴追記タスク追加
          recordTask[vI] = {'getDataAt':time, 'tweet':'notTweetItsNewPlaylistData', 'localPlNo':loPlNo} 

    #nextPageTokenの有無
    pageTokenGet = 'nextPageToken' in resData
    if pageTokenGet:
      pageToken = resData['nextPageToken']

# 追加された公開/限定公開動画videoId取得完了(taskVideoIds)
#videoId詳細データ取得(通知内容準備)

#データ一時保存
#SQL文字列生成
reqSqlStr = []
#もし履歴追記タスクに項目があれば
if recordTask != {}:
  for recId in recordTask:
    reqSqlStr.append(f"INSERT INTO videoids (id, getdataat, tweet, localplno) VALUES ('{recId}', '{recordTask[recId]['getDataAt']}', '{recordTask[recId]['tweet']}', {recordTask[recId]['localPlNo']})")
  #データベース送信
  qnly.DBSQL(HerokuDBUrl, reqSqlStr)

#待機中の項目をtaskVideoIdsに追加
if len(waitingVideoIdsData) != 0:
  for wtgVid in waitingVideoIdsData:
    taskVideoIds[wtgVid[0]] = {'localPlNo':wtgVid[1], 'waiting':True}

#taskVideoIdsの項目(ツイート項目)がある場合のみ
if len(taskVideoIds) != 0:

  #taskVideoIdsの項目をtaskVideoIdとして項目ごとに実行
  #回数制限カウンタ
  tweetCount = 0
  tweetCountOver = 0

  for taskVideoId in taskVideoIds:
    videoData = qnly.getVideoData(part='snippet,liveStreamingDetails,status', videoIds=taskVideoId, apiKey=YTApiKey)
    #データの分類/簡素化
    vDSnippet = videoData['items'][0]['snippet']
    vDStatus = videoData['items'][0]['status']
    vDLSD = videoData['items'][0]['liveStreamingDetails']
    #各種データの取り出し
    #title(タイトル)
    videoTitle = vDSnippet['title']
    #liveBroadcastContent(配信状態)
    lbc = vDSnippet['liveBroadcastContent']
    #uploadStatus(ライブ配信/プレ公判断)
    uls = vDStatus['uploadStatus']

    #待機中かどうか情報取得
    waitingThisId = taskVideoIds[taskVideoId]['waiting']

    #uploadStatus(uls)で配信/プレミア公開判定

    loPlSlNo = taskVideoIds[taskVideoId]['localPlNo']
    if uls == 'uploaded': #配信前/配信中はuploaded、プレ公/配信終了後はprocessedになる<-ツイート有無判断

      #事故対策回数制限
      if tweetCount <= tweetLimit:

        #カウント追加
        tweetCount += 1

        #Info(案内文データベース)を取得
        infoData = qnly.DBSQL(HerokuDBUrl, "SELECT * FROM info", True)
        #もし項目があれば
        if len(infoData) != 0:
          #リストの一番最初の項目のデータを取り出す
          infoNo = infoData[0][0]
          infoText = infoData[0][1]
        else:
          infoNo = infoText = None

        #liveBroadcastContentで配信の状態判定
        if lbc == 'live': #配信中であれば

          #時刻に合わせて表示させる文字列設定
          timeCondition = '配信開始'
          #取得データにactualStartTime(配信開始時刻)が含まれているか確認
          if 'actualStartTime' in vDLSD:
            #配信開始時刻を取得
            startTime = vDLSD['actualStartTime']

          else: #配信開始時刻が含まれていなければ
            startTime = 'error'

          #ツイートタイトル設定
          tweetTitle = 'ただ今ライブ配信中！'

        elif not stopNotify: #ライブ配信前かつ通知制限時間帯でないならば
          
          #時刻に合わせて表示させる文字列設定
          timeCondition = '配信開始予定'
          #取得データにscheduledStartTime(配信開始予定時刻)が含まれているか確認
          if 'scheduledStartTime' in vDLSD:
            #配信開始予定時刻を取得
            startTime = vDLSD['scheduledStartTime']

          else: #配信開始予定時刻が含まれていなければ
            startTime = 'error'

          #liveBroadcastContentで配信の状態判定
          if lbc == 'upcoming': #配信開始予定であれば
            #ツイートタイトル設定
            tweetTitle = '配信予定情報'
          
          else: #配信開始予定でなければ(例外用)
            #ツイートタイトル設定
            tweetTitle = '再生リスト更新情報'
          
          #待機中だったものは
          if waitingThisId:
            tweetTitle = '🌅７時までの' + tweetTitle

        else: #配信中でなく通知制限時間帯ならば
          #すでに待機中idsに記録されていなければ
          if not taskVideoId in waitingVideoIds:
            #取得データにscheduledStartTime(配信開始予定時刻)が含まれているか確認
            if 'scheduledStartTime' in vDLSD:
              #配信開始予定時刻を取得
              startTime = vDLSD['scheduledStartTime']
            else: #配信開始予定時刻が含まれていなければ
              startTime = 'error'
            #データベースに追記
            qnly.DBSQL(HerokuDBUrl, f"INSERT INTO waiting (id, localplno) VALUES ('{taskVideoId}', {loPlSlNo})")
            #ディスコ送信
            qnly.sendDiscord(dcUrl, f'**Find new video but now is non notify time**\n> VideoId: {taskVideoId}\n> GetAt: {qnly.getNowTime()}\n> LocalPlNo: {loPlSlNo}')
          #この繰り返しで以下を実行しない
          continue

        #配信開始(予定)時刻を取得できているか確認
        if startTime != 'error':
          #配信開始(予定)時刻を文字列に変換
          startTimeText = qnly.ytTimeConbour(startTime)
          #ツイート本文時間案内文字列生成
          tweetTimeText = f'\n{startTimeText} {timeCondition}'
          #もし配信予定かつ待機中でなければ
          if lbc == 'upcoming' and not waitingThisId:
            #通知タイトルを開始予定時刻を組み込んだものにする
            titleTimeText = qnly.ytTimeConbourForTitle(startTime)
            tweetTitle = f'{titleTimeText}から配信予定!'

        #取得できていなければ
        else:
          tweetTimeText = ''

        #案内文生成
        if infoNo != None:
          tweetInfoText = f'\n[お知らせ] {infoText}'
        else:
          tweetInfoText = ''

        #ツイート文形成
        """
        🍌配信予定情報🌟

        〈動画タイトル〉
        youtu.be/[videoId]
        M月dd日 h時mm分 配信開始予定 <<<tweetTimeTextに改行コードも含める
        [お知らせ] お知らせ本文 <<<データがある場合のみ/改行コードも含める
        """

        successTweet = False
        
        #ツイートエラー時は動画タイトルを20文字に制限してリトライ
        for trycount in range(2):
          if not successTweet:
            tweetText = f'🍌{tweetTitle}🌟\n{videoTitle}\nyoutu.be/{taskVideoId}{tweetTimeText}{tweetInfoText}'
            pram = {'text':tweetText}
            
            #ツイート送信
            tweetRet = qnly.sendTweet(cK=cK, cS=cS, aT=aT, aTS=aTS, pram=pram)
            #ツイートエラー判断
            if tweetRet != 'HTTPREQUESTERROR':
              successTweet = True
            
              if tweetInfoText == '':
                successTweetInfo = False
              else:
                successTweetInfo = True
                
            else:
              successTweet = False
              videoTitle = videoTitle[:20]
              videoTitle += '...'
              tweetInfoText = ''
              successTweetInfo = False

        #履歴更新
        time = qnly.getNowTime()
        if successTweet:
          #履歴書き込み
          qnly.DBSQL(HerokuDBUrl, f"INSERT INTO videoids (id, getdataat, tweet, localplno) VALUES ('{taskVideoId}', '{time}', 'successed!', {loPlSlNo})")

          #Discord送信
          try:
            tweetId = tweetRet['data']['id']
          except:
            tweetId = 'None'

          if infoNo != None:
            if successTweetInfo:
              DCInfo = 'Success!'
            else:
              DCInfo = 'Failed'
          else:
            DCInfo = 'No info Data'

          sendDCText = f'**Send Tweet is successed!**\n{videoTitle}\nhttps://youtu.be/{taskVideoId}\n{tweetTimeText}\n> TweetID: {tweetId}\n> GetAt: {time}\n> LocalPlaylistNo: {loPlSlNo}\n> Send INFO: {DCInfo}'
          qnly.sendDiscord(dcUrl, sendDCText)

          #待機中データ削除
          qnly.DBSQL(HerokuDBUrl, f"DELETE FROM waiting WHERE id='{taskVideoId}'")

        else:
          #履歴書き込み
          sendDCText = f'**Send Tweet is failed.**\nhttps://youtu.be/{taskVideoId}\n> GetAt: {time}\n> LocalPlaylistNo: {loPlSlNo}'
          qnly.sendDiscord(dcUrl, sendDCText)
        
        #案内データ更新
        if successTweetInfo and infoNo != None:
          qnly.DBSQL(HerokuDBUrl, f"DELETE FROM info WHERE no={infoNo}")

      else:
        tweetCountOver += 1
        qnly.sendDiscord(dcUrl, f'**Send Tweet is failed.**\n> ID: {taskVideoId}\n> TweetCount: {tweetCount}')

    #プレ公もしくは配信終了後なら
    else:
      #履歴更新
      #待機リストのIDなら
      if waitingThisId:
        qnly.DBSQL(HerokuDBUrl, f"DELETE FROM waiting WHERE id='{taskVideoId}'")
      qnly.DBSQL(HerokuDBUrl, f"INSERT INTO videoids (id, getdataat, tweet, localplno) VALUES ('{taskVideoId}', '{time}', 'uploadStatus is [processed]', {loPlSlNo})")
      sendDCText = f'**Get data is not live now.**\nhttps://youtu.be/{taskVideoId}\n> GetAt: {time}\n> LocalPlNo: {loPlSlNo}'

if len(changedPls) != 0:
  sendDCText = '**Playlist is changed.**'
  for cPl in changedPls:
    sendDCText += f'\n> https://www.youtube.com/playlist?list={cPl}'
  qnly.sendDiscord(dcUrl, sendDCText)
