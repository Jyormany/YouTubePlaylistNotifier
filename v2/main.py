import datetime
import os
import function as qnly

"""
使用するデータベース

データベース
videoids :非公開等を除く検知した動画と状態
  └- id : TEXT / Video ID

playlists :検知させる再生リストのIDと情報
  ├- id : TEXT / 変更を検知させる再生リストID <-検知再生リスト追加時はこの項目のみを手入力で追加
  └- etag : TEXT / 再生リストから最後に取得したEtag

info :通知に添付する連絡文
  └- text : TEXT / 連絡本文 <-文字数超過でツイートに失敗するとキャンセルされる <-連絡文データはツイート成功時に削除

waiting :指定時間後に通知予定の指定時間中に検知した再生リストの変更リスト
  └- id : TEXT / Video ID

subs :最後に通知したチャンネル登録者数
  └- subs : INT-8bit / 登録者数

emoji :通知文に使用する絵文字(useがTrueで一番上の項目を使用)
  ├- left : TEXT / 左側の絵文字
  ├- right : TEXT / 右側の絵文字
  └- use : bool / 使用可否
"""

#環境変数として読み込む機密情報============================

#YouTube API
YT_API_KEY = os.environ.get("YOUTUBE_API_KEY")
#チャンネルID
CHANNEL_ID = os.environ.get("CHANNEL_ID")

#Twitter API
#ConsumerKey
TWITTER_CONS_KEY = os.environ.get("TWITTER_CONSUMER_KEY")
#ConsumerSecret
TWITTER_CONS_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
#AccessToken
TWITTER_ACES_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
#AccessTokenSecret
TWITTER_ACES_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

#Discord Webhook
DC_URL = os.environ.get("DISCORD_URL")

#Database URL(変更される可能性あり/Herokuサイト環境変数から読み込む)
DATABASE_URL = os.environ.get("DATABASE_URL")

#====================================================

#事故対策/ツイート送信回数制限(指定回数を超えるとツイートしない)
TWEET_LIMIT = 10

#通知制限時間帯設定(配信開始を除く通知を停止/止めている間の通知は設定時間帯後に送信される/日付は跨げない/日本時間)
#通知停止時刻(24時間表記のx時丁度から)
NOTIFY_STOP_TIME = 1
#通知開始時刻(24時間表記のx時前まで)
NOTIFY_START_TIME = 7

#失敗時に通知
try:

  #現在時刻取得(日本時間)
  nowTimeHour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).hour
  #通知制限時間帯であれば
  if NOTIFY_STOP_TIME <= nowTimeHour < NOTIFY_START_TIME:
    STOP_NOTIFY = True
  else:
    STOP_NOTIFY = False
  del nowTimeHour

  #新しいvideoIdを取得する

  #更新検知対象の再生リストID取得
  plIdsData = qnly.DBSQL(DATABASE_URL, 'SELECT * FROM playlists', True)
  print(plIdsData)

  #過去に検知済のvideoID取得
  viIdHisRaw = qnly.DBSQL(DATABASE_URL, 'SELECT * FROM videoids', True)
  #リスト配列化
  viIdHis = []
  for viIdHisData in viIdHisRaw:
      viIdHis.append(viIdHisData[0])
  del viIdHisRaw
  print("viIdHis==")
  print(viIdHis)

  #通知停止時間帯中に検知したvideoId取得
  waitingVideoIdsRaw = qnly.DBSQL(DATABASE_URL, 'SELECT * FROM waiting', True)
  waitingVideoIds = []
  for waitViIdsData in waitingVideoIdsRaw:
      waitingVideoIds.append(waitViIdsData[0])
  print("waitingVideoIds==")
  print(waitingVideoIds)

  #変数定義
  newViId = [] #新規追加予定リスト
  taskVideoIds = [] #変更を検知したvideoIDリスト配列
  recordTask = [] #履歴追記タスクリスト配列
  addTweetTitle = "" #ツイートの最初の行に追加される文字列
  updateSubs = False #登録者数更新有無


  #再生リストの数繰り返し
  for plIdData in plIdsData:
    #ID取り出し
    plId = plIdData[0]
    print("plId==")
    print(plId)
    #Etag取り出し
    oldEtag = plIdData[1]
    #localPlNo取り出し
    #loPlNo = plIdData[3]

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
      resData = qnly.getPlData(part=part, plIds=plId, apiKey=YT_API_KEY, pageToken=pageToken)
      #取得回数カウント
      plLoad += 1

      #pageTokenループ1回目なら
      if plLoad == 1:
        #記録時刻取得
        #time = qnly.getNowTime()
        #etag取得
        nowEtag = resData['etag']
        #この再生リストのデータは初取得か？
        if oldEtag == None or '':
          newPl = True
          #データベースetag更新
          qnly.DBSQL(DATABASE_URL, f"UPDATE playlists SET etag='{nowEtag}' WHERE id='{plId}'")
        
        else:
          newPl = False
            
          #Etag変更確認
          #変更がなければスキップ
          if oldEtag == nowEtag:
            #pageToken while から離脱
            break

          #変更があれば継続＆DB更新
          else:
            #データベース更新
            qnly.DBSQL(DATABASE_URL, f"UPDATE playlists SET etag='{nowEtag}' WHERE id='{plId}'")

      

      #videoIdの数だけ繰り返し
      for item in resData['items']:
        #videoIdを取得
        vI = item['contentDetails']['videoId']
        #privasyStatus取得(公開設定)
        pS = item['status']['privacyStatus']
        #公開設定の判別/'private'(非公開)または'privacyStatusUnspecified'(削除済)ではなく、履歴と取得済みID(他の再生リストとのダブり防止)に記録がなければ
        if pS != 'private' and pS != 'privacyStatusUnspecified' and (vI in viIdHis) == False and (vI in newViId) == False:
          #履歴追記
          #現在時刻取得
          time = qnly.getNowTime()

          #取得済みデータ追記
          newViId.append(vI)

          #通知対象であれば(新しく追加された再生リストの情報ではない)
          if not newPl:
            #通知タスクに追記
            taskVideoIds.append(vI)

          else:#新しく追加された再生リストのデータのため通知しない
            #履歴追記タスク追加
            recordTask.append(vI)

      #nextPageTokenの有無を確認
      pageTokenGet = 'nextPageToken' in resData
      #あれば次の繰り返しに引き継ぎ
      if pageTokenGet:
        pageToken = resData['nextPageToken']

  del plIdsData

  # 追加された公開/限定公開動画videoId取得完了(taskVideoIds)
  #videoId詳細データ取得(通知内容準備)

  #データ一時保存
  #SQL文字列生成
  reqSqlStr = []
  #もし履歴追記タスクに項目があれば
  if len(recordTask) != 0:
    for recId in recordTask:
      reqSqlStr.append(f"INSERT INTO videoids (id) VALUES ('{recId}')")
    #データベース送信
    qnly.DBSQL(DATABASE_URL, reqSqlStr)

  #待機中の項目がありtaskVideoIdsに無ければ追加
  if len(waitingVideoIds) != 0:
    for wtgVid in waitingVideoIds:
      if not wtgVid in taskVideoIds:
          taskVideoIds.append(wtgVid)
  print("taskVideoIds==")
  print(taskVideoIds)
  #taskVideoIdsの項目(ツイート項目)がある場合のみ
  if len(taskVideoIds) != 0:

    #taskVideoIdsの項目をtaskVideoIdとして項目ごとに実行
    #回数制限カウンタ
    tweetCount = 0
    tweetCountOver = 0

    for taskVideoId in taskVideoIds:
      videoData = qnly.getVideoData(part='snippet,liveStreamingDetails,status', videoIds=taskVideoId, apiKey=YT_API_KEY)
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

      #待機中だったかどうか情報取得
      waitingThisId = taskVideoId in waitingVideoIds
      print(f'waiting=={waitingThisId}')

      #uploadStatus(uls)で配信/プレミア公開判定
      if uls == 'uploaded': #配信前/配信中はuploaded、プレ公/配信終了後はprocessedになる<-ツイート有無判断

        #事故対策回数制限
        if tweetCount <= TWEET_LIMIT:

          #カウント追加
          tweetCount += 1

          #Info(案内文データベース)を取得
          infoData = qnly.DBSQL(DATABASE_URL, "SELECT * FROM info", True)
          #もし項目があれば
          if len(infoData) != 0:
            #リストの一番最初の項目のデータを取り出す
            infoText = infoData[0][0]
            infoUuid = infoData[0][1]
          else:
            infoText = None
            infoUuid = None
          
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

          elif not STOP_NOTIFY: #ライブ配信前かつ通知制限時間帯でないならば
            
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
              tweetTitle = f'🌅{NOTIFY_START_TIME}時までの{tweetTitle}'

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
              qnly.DBSQL(DATABASE_URL, f"INSERT INTO waiting (id) VALUES ('{taskVideoId}')")
              #ディスコ送信
              qnly.sendDiscord(DC_URL, f'**Find new video but now is non notify time**\n> VideoId: {taskVideoId}\n> GetAt: {qnly.getNowTime()}')
            #この繰り返しで以下を実行しない
            continue

          #配信開始(予定)時刻を取得できているか確認
          if startTime != 'error':
            #配信開始(予定)時刻を文字列に変換
            startTimeText = qnly.ytTimeConbour(startTime)
            #ツイート本文時間案内文字列生成
            tweetTimeText = f'\n{startTimeText} {timeCondition}'
            #もし配信予定でなければ
            if lbc == 'upcoming':
              #通知タイトルを開始予定時刻を組み込んだものにする
              titleTimeText = qnly.ytTimeConbourForTitle(startTime)
              
              #待機中だったら待機中明けタイトルを一番上の行に移動
              if waitingThisId:
                  addTweetTitle = f'{tweetTitle}\n'
              
              tweetTitle = f'{titleTimeText}から配信予定!'
              

          #取得できていなければ
          else:
            tweetTimeText = ''

          #登録者数チェック
          nowSubs = int()
          tweetSubsInfoText = ""
          try:
              updateSubs = False
              #現在の登録者数を取得
              nowSubs = qnly.getSubscriversCount(CHANNEL_ID, YT_API_KEY)

              #データベースから過去の登録者数を取得
              beforeSubsRaw = qnly.DBSQL(DATABASE_URL, 'SELECT * FROM subs', True)

              subsCheckError = False
              #データベースに記録されているか確認
              #記録が無ければ
              if len(beforeSubsRaw) == 0:
                  #データを記録
                  qnly.DBSQL(DATABASE_URL, f"INSERT INTO subs (count) VALUES ('{nowSubs}')")
                  print("SubsDB-Insert")

              #記録件数が1で無ければ
              elif len(beforeSubsRaw) != 1:
                  subsCheckError = True
                  print("DB-subsRowsOver")

              else:
                  #取得したデータを取り出す
                  beforeSubs = beforeSubsRaw[0][0]#int型
                  print(f"{beforeSubs}->{nowSubs}")

                  #もし増加していたら
                  if beforeSubs < nowSubs:
                      tweetSubsInfoText = ""
                      #1000人以上増加しているか確認
                      if (nowSubs - beforeSubs) >= 1000:

                          updateSubs = True

                          nowSubsOverTenThousandStr = ""
                          nowSubsOverThousandStr = ""
                          subsCongFirstStr = ""
                          subsCongLastStr = ""
                          #登録者数を文字列に変換(xx万y千zzz人)
                          #x万人
                          if nowSubs >= 10000:

                              nowSubsOverTenThousandStr = f'{str(nowSubs)[:-4]}万'

                          else:
                              nowSubsOverTenThousandStr = ""
                              
                          #x千人
                          if nowSubs >= 1000:
                              nowSubsOverThousand = str(nowSubs)[-4]
                              if nowSubsOverThousand == "0":
                                  nowSubsOverThousandStr = ""
                              else:
                                  nowSubsOverThousandStr = str(nowSubs)[-4:]
                          
                              #文末生成
                              #X十万人丁度なら
                              if str(nowSubs)[-5] == "00000":
                                  subsCongFirstStr = "㊗️🎊"
                                  subsCongLastStr = "🎉🥳"
                              #X万人丁度なら
                              elif str(nowSubs)[-4:] == "0000":
                                  subsCongFirstStr = "🎊"
                                  subsCongLastStr = "🥳"
                              else:
                                  subsCongFirstStr = ""
                                  subsCongLastStr = "！"

                          #文字列生成
                          tweetSubsInfoText = f'《{subsCongFirstStr}登録者数{nowSubsOverTenThousandStr}{nowSubsOverThousandStr}人突破{subsCongLastStr}》\n'

          #エラー時処理
          except Exception as e:
              print(e)
              tweetSubsInfoText = ""

          #案内文生成
          if infoText != None:
            tweetInfoText = f'\n[お知らせ] {infoText}'
          else:
            tweetInfoText = ''

          #ツイート文形成
          """
          《登録者数**人突破!》 <<<更新がある場合のみ/改行コードも含める
          🍌配信予定情報🌟  <<<絵文字はDBから取得しTrueの項目があれば使用
          〈動画タイトル〉
          youtu.be/[videoId]
          M月dd日 h時mm分 配信開始予定 <<<tweetTimeTextに改行コードも含める
          [お知らせ] お知らせ本文 <<<データがある場合のみ/改行コードも含める
          """

          successTweet = False

          leftEmoji = "🍌"
          rightEmoji = "🌟"
          try:
            #通知タイトル絵文字取得
            emojiList = qnly.DBSQL(DATABASE_URL, 'SELECT * FROM emoji', True)
            
            #リストの項目数繰り返し
            for emoji in emojiList:
              if emoji[2] == True:
                leftEmoji = emoji[0]
                rightEmoji = emoji[1]
                break

          except Exception as e:
            print("emoji get error.")


          
          #ツイートエラー時は動画タイトルを最初の20文字に制限・お知らせ文なしでリトライ
          for trycount in range(2):
            if not successTweet:
              tweetText = f'{tweetSubsInfoText}{addTweetTitle}{leftEmoji}{tweetTitle}{rightEmoji}\n{videoTitle}\nyoutu.be/{taskVideoId}{tweetTimeText}{tweetInfoText}'
              pram = {'text':tweetText}
              
              #ツイート送信
              tweetRet = qnly.sendTweet(cK=TWITTER_CONS_KEY, cS=TWITTER_CONS_SECRET, aT=TWITTER_ACES_TOKEN, aTS=TWITTER_ACES_TOKEN_SECRET, pram=pram)
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
            qnly.DBSQL(DATABASE_URL, f"INSERT INTO videoids (id) VALUES ('{taskVideoId}')")

            #Discord送信
            try:
              tweetId = tweetRet['data']['id']
            except:
              tweetId = 'None'

            if infoText != None:
              if successTweetInfo:
                DCInfo = 'Success!'
              else:
                DCInfo = 'Failed'
            else:
              DCInfo = 'No info Data'

            sendDCText = f'**Send Tweet is successed!**\n{videoTitle}\nhttps://youtu.be/{taskVideoId}\n{tweetTimeText}\n> TweetID: {tweetId}\n> GetAt: {time}\n> Send INFO: {DCInfo}\n> NowSubs: {nowSubs}\n> UpdateSubs: {updateSubs}'
            qnly.sendDiscord(DC_URL, sendDCText)

            #データベース更新
            if updateSubs:
              qnly.DBSQL(DATABASE_URL, f"UPDATE subs SET count={nowSubs} WHERE count={beforeSubs}")

            #待機中データ削除
            if waitingThisId:
              qnly.DBSQL(DATABASE_URL, f"DELETE FROM waiting WHERE id='{taskVideoId}'")

          else:
            #履歴書き込み
            sendDCText = f'**Send Tweet is failed.**\nhttps://youtu.be/{taskVideoId}\n> GetAt: {time}'
            qnly.sendDiscord(DC_URL, sendDCText)
          
          #案内データ削除
          if successTweetInfo:
            qnly.DBSQL(DATABASE_URL, f"DELETE FROM info WHERE uuid='{infoUuid}'")

        else:
          tweetCountOver += 1
          qnly.sendDiscord(DC_URL, f'**Send Tweet is failed.**\n> ID: {taskVideoId}\n> TweetCount: {tweetCount}\n> TweetCount Over: {tweetCountOver}')

      #プレ公もしくは配信終了後なら
      else:
        #履歴更新
        #待機リストのIDなら
        if waitingThisId:
          qnly.DBSQL(DATABASE_URL, f"DELETE FROM waiting WHERE id='{taskVideoId}'")
        qnly.DBSQL(DATABASE_URL, f"INSERT INTO videoids (id) VALUES ('{taskVideoId}')")
        sendDCText = f'**Get data is not live now.**\nhttps://youtu.be/{taskVideoId}\n> GetAt: {time}'

except Exception as e:
  print('runningError')
  import traceback
  qnly.sendDiscord(DC_URL, f'**RUN PROGRAM FAILED**\n\nError:\n```console\n{e}```\nTraceback:\n```console\n{traceback.format_exc}```\nargs:\n```console\n{e.args}```')
