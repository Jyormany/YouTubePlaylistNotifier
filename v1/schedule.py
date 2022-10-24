import datetime
from time import sleep
import subprocess

#実行間隔/回数設定
#実行間隔分数
exeInterval = 2
#実行回数
exeCount = 5

runTimes = [0]
#現在時刻取得
nowClkTime = datetime.datetime.now()
for i in range(exeCount - 1):
    #実行予定時刻追加
    thisWait = exeInterval * (i + 1)
    runTimes.append(nowClkTime + datetime.timedelta(minutes=thisWait))

for thisTime in runTimes:
    if thisTime == 0:
        None
    else:
        #時間まで待機
        #秒数取得
        waitTime = int((thisTime - datetime.datetime.now()).total_seconds())
        #まだ指定時間を過ぎていないなら
        if waitTime >= 0:
            sleep(waitTime)

    #プログラム実行
    command = ['python','main.py']
    run = subprocess.Popen(command)
    run.communicate()
