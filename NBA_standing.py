import requests
from datetime import datetime
import os
from unicodedata import east_asian_width

SEASON_LABEL = "2025-26"
ESPN_SEASON = "2026"
STANDARD_COLUMNS = [8, 32, 8, 8, 10, 10, 14, 14]
NBA_COM_COLUMNS = STANDARD_COLUMNS + [14]
BACKUP_COLUMNS = [8, 32, 8, 8, 10, 17, 14, 14]

def display_width(value):
    """
    計算終端機顯示寬度，中文全形字通常佔 2 格。
    """
    return sum(2 if east_asian_width(char) in ('F', 'W') else 1 for char in str(value))

def pad_right(value, width):
    text = str(value)
    padding = max(width - display_width(text), 0)
    return text + ' ' * padding

def format_table_row(values, widths):
    return ''.join(pad_right(value, width) for value, width in zip(values, widths))

def separator(widths):
    return "-" * sum(widths)

def espn_stats_map(stats):
    """
    將 ESPN stats list 轉成以 name/displayName 為 key 的 dict，避免欄位順序變動造成資料錯位。
    """
    result = {}
    for stat in stats:
        name = stat.get('name')
        display_name = stat.get('displayName')
        if name:
            result[name] = stat
        if display_name:
            result[display_name] = stat
    return result

def get_espn_stat(stats_by_name, name, default='-'):
    stat = stats_by_name.get(name, {})
    return stat.get('displayValue', default)

def get_espn_stat_int(stats_by_name, name, default=0):
    stat = stats_by_name.get(name, {})
    value = stat.get('value')
    if value is None:
        value = stat.get('displayValue', default)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def espn_standings_sort_key(team):
    stats_by_name = espn_stats_map(team.get('stats', []))
    win_percent = stats_by_name.get('winPercent', {}).get('value', 0)
    wins = get_espn_stat_int(stats_by_name, 'wins')
    losses = get_espn_stat_int(stats_by_name, 'losses')
    return (-float(win_percent or 0), -wins, losses)

def save_to_log(data, source="NBA.com"):
    """
    將戰績數據保存到日誌文件
    """
    log_dir = "nba_logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 使用時間戳作為檔名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"nba_standings_{timestamp}.log")
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"{'='*100}\n")
            f.write(f"NBA 戰績表 ({SEASON_LABEL} 賽季)\n")
            f.write(f"數據來源: {source}\n")
            f.write(f"獲取時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*100}\n\n")
            
            if source == "NBA.com" and data:
                result_sets = data.get('resultSets', [])
                if result_sets:
                    standings_data = result_sets[0]
                    headers_list = standings_data.get('headers', [])
                    rows = standings_data.get('rowSet', [])
                    idx_map = {header: idx for idx, header in enumerate(headers_list)}
                    
                    for conf in ['East', 'West']:
                        conf_name = "Eastern Conference (東區)" if conf == 'East' else "Western Conference (西區)"
                        f.write(f"\n{conf_name}\n")
                        f.write(separator(NBA_COM_COLUMNS) + "\n")
                        f.write(format_table_row(['排名', '球隊', '勝', '敗', '勝率', '勝差', '主場', '客場', '近10場'], NBA_COM_COLUMNS) + "\n")
                        f.write(separator(NBA_COM_COLUMNS) + "\n")
                        
                        conf_teams = [row for row in rows if row[idx_map.get('Conference', 0)] == conf]
                        conf_teams.sort(key=lambda x: x[idx_map.get('WinPCT', 0)], reverse=True)
                        
                        for rank, team in enumerate(conf_teams, 1):
                            team_city = team[idx_map.get('TeamCity', 0)]
                            team_name = team[idx_map.get('TeamName', 0)]
                            full_name = f"{team_city} {team_name}"
                            wins = team[idx_map.get('WINS', 0)]
                            losses = team[idx_map.get('LOSSES', 0)]
                            win_pct = f"{team[idx_map.get('WinPCT', 0)]:.3f}"
                            games_back = team[idx_map.get('ConferenceGamesBack', 0)]
                            home_record = team[idx_map.get('HOME', 0)]
                            road_record = team[idx_map.get('ROAD', 0)]
                            last_10 = team[idx_map.get('L10', 0)]
                            
                            gb_str = '-' if games_back == 0 else f"{games_back:.1f}"
                            
                            f.write(format_table_row([rank, full_name, wins, losses, win_pct, gb_str, home_record, road_record, last_10], NBA_COM_COLUMNS) + "\n")
            
            elif source == "ESPN" and data:
                for conference in data.get('children', []):
                    conf_name = conference.get('name', '')
                    standings = conference.get('standings', {}).get('entries', [])
                    
                    if conf_name:
                        f.write(f"\n{conf_name}\n")
                        f.write(separator(STANDARD_COLUMNS) + "\n")
                        f.write(format_table_row(['排名', '球隊', '勝', '敗', '勝率', '勝差', '主場', '客場'], STANDARD_COLUMNS) + "\n")
                        f.write(separator(STANDARD_COLUMNS) + "\n")
                        
                        standings.sort(key=espn_standings_sort_key)

                        for rank, team in enumerate(standings, 1):
                            stats = team.get('stats', [])
                            stats_by_name = espn_stats_map(stats)
                            team_info = team.get('team', {})
                            
                            wins = get_espn_stat_int(stats_by_name, 'wins')
                            losses = get_espn_stat_int(stats_by_name, 'losses')
                            win_pct = get_espn_stat(stats_by_name, 'winPercent', '.000')
                            games_back = get_espn_stat(stats_by_name, 'gamesBehind')
                            home_record = get_espn_stat(stats_by_name, 'Home', '0-0')
                            road_record = get_espn_stat(stats_by_name, 'Road', '0-0')
                            team_name = team_info.get('displayName', 'Unknown')
                            
                            f.write(format_table_row([rank, team_name, wins, losses, win_pct, games_back, home_record, road_record], STANDARD_COLUMNS) + "\n")
            
            f.write(f"\n{'='*100}\n")
            f.write(f"日誌已保存\n")
        
        print(f"\n✓ 日誌已保存至: {log_file}")
        return log_file
    
    except Exception as e:
        print(f"\n✗ 保存日誌時發生錯誤: {e}")
        return None

def fetch_nba_standings_nba_com():
    """
    使用 NBA.com 官方 API 抓取 NBA 戰績表
    """
    # NBA.com stats API
    url = "https://stats.nba.com/stats/leaguestandings"
    
    params = {
        'LeagueID': '00',  # NBA
        'Season': SEASON_LABEL,
        'SeasonType': 'Regular Season',
        'SeasonYear': ''
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://www.nba.com',
        'Referer': 'https://www.nba.com/',
        'x-nba-stats-origin': 'stats',
        'x-nba-stats-token': 'true'
    }
    
    try:
        print("正在連接 NBA.com 官方 API...")
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"HTTP 狀態碼: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        
        print(f"\n{'='*100}")
        print(f"NBA 戰績表 ({SEASON_LABEL} 賽季) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"資料來源: NBA.com 官方")
        print(f"{'='*100}\n")
        
        # 解析 NBA.com 的數據結構
        result_sets = data.get('resultSets', [])
        if not result_sets:
            print("無法獲取數據")
            return None
        
        standings_data = result_sets[0]
        headers_list = standings_data.get('headers', [])
        rows = standings_data.get('rowSet', [])
        
        # 建立索引映射
        idx_map = {header: idx for idx, header in enumerate(headers_list)}
        
        # 分東西區顯示
        for conf in ['East', 'West']:
            conf_name = "Eastern Conference (東區)" if conf == 'East' else "Western Conference (西區)"
            print(f"\n{conf_name}")
            print(separator(NBA_COM_COLUMNS))
            print(format_table_row(['排名', '球隊', '勝', '敗', '勝率', '勝差', '主場', '客場', '近10場'], NBA_COM_COLUMNS))
            print(separator(NBA_COM_COLUMNS))
            
            # 篩選該分區的球隊
            conf_teams = [row for row in rows if row[idx_map.get('Conference', 0)] == conf]
            # 按勝率排序
            conf_teams.sort(key=lambda x: x[idx_map.get('WinPCT', 0)], reverse=True)
            
            for rank, team in enumerate(conf_teams, 1):
                team_city = team[idx_map.get('TeamCity', 0)]
                team_name = team[idx_map.get('TeamName', 0)]
                full_name = f"{team_city} {team_name}"
                wins = team[idx_map.get('WINS', 0)]
                losses = team[idx_map.get('LOSSES', 0)]
                win_pct = f"{team[idx_map.get('WinPCT', 0)]:.3f}"
                games_back = team[idx_map.get('ConferenceGamesBack', 0)]
                home_record = team[idx_map.get('HOME', 0)]
                road_record = team[idx_map.get('ROAD', 0)]
                last_10 = team[idx_map.get('L10', 0)]
                
                # 格式化勝差
                gb_str = '-' if games_back == 0 else f"{games_back:.1f}"
                
                print(format_table_row([rank, full_name, wins, losses, win_pct, gb_str, home_record, road_record, last_10], NBA_COM_COLUMNS))
        
        return data
        
    except requests.exceptions.Timeout:
        print("連線逾時，嘗試使用備用方案...")
        return fetch_nba_standings_backup()
    except requests.exceptions.RequestException as e:
        print(f"請求錯誤: {e}")
        return None
    except Exception as e:
        print(f"發生錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

def fetch_nba_standings_espn():
    """
    使用 ESPN API 抓取 NBA 戰績表（更穩定）
    """
    # 2025-26 賽季
    url = f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={ESPN_SEASON}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print("正在連接 ESPN API...")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"HTTP 狀態碼: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        
        print(f"\n{'='*100}")
        print(f"NBA 戰績表 ({SEASON_LABEL} 賽季) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*100}\n")
        
        # 處理每個分區的戰績
        for conference in data.get('children', []):
            conf_name = conference.get('name', '')
            standings = conference.get('standings', {}).get('entries', [])
            
            if conf_name:
                print(f"\n{conf_name}")
                print(separator(STANDARD_COLUMNS))
                print(format_table_row(['排名', '球隊', '勝', '敗', '勝率', '勝差', '主場', '客場'], STANDARD_COLUMNS))
                print(separator(STANDARD_COLUMNS))
                
                standings.sort(key=espn_standings_sort_key)

                for rank, team in enumerate(standings, 1):
                    stats = team.get('stats', [])
                    stats_by_name = espn_stats_map(stats)
                    team_info = team.get('team', {})
                    
                    wins = get_espn_stat_int(stats_by_name, 'wins')
                    losses = get_espn_stat_int(stats_by_name, 'losses')
                    win_pct = get_espn_stat(stats_by_name, 'winPercent', '.000')
                    games_back = get_espn_stat(stats_by_name, 'gamesBehind')
                    home_record = get_espn_stat(stats_by_name, 'Home', '0-0')
                    road_record = get_espn_stat(stats_by_name, 'Road', '0-0')
                    
                    team_name = team_info.get('displayName', 'Unknown')
                    
                    print(format_table_row([rank, team_name, wins, losses, win_pct, games_back, home_record, road_record], STANDARD_COLUMNS))
        
        return data
        
    except requests.exceptions.Timeout:
        print("連線逾時，嘗試使用備用方案...")
        return fetch_nba_standings_backup()
    except requests.exceptions.RequestException as e:
        print(f"請求錯誤: {e}")
        return None
    except Exception as e:
        print(f"發生錯誤: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

def fetch_nba_standings_backup(max_retries=2):
    """
    備用方案：使用 nba_api 套件 (含重試機制)
    """
    try:
        from nba_api.stats.endpoints import leaguestandingsv3
        import time
        
        for attempt in range(max_retries):
            try:
                print(f"使用 nba_api 套件 (嘗試 {attempt + 1}/{max_retries})...")
                
                # 設定適當的超時時間
                standings = leaguestandingsv3.LeagueStandingsV3(
                    season=SEASON_LABEL,
                    timeout=20
                )
                data = standings.get_dict()
                
                result_set = data['resultSets'][0]
                headers = result_set['headers']
                rows = result_set['rowSet']
                
                print(f"\n{'='*100}")
                print(f"NBA 戰績表 ({SEASON_LABEL} 賽季) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*100}\n")
                
                # 分組顯示東西區
                for conf in ['East', 'West']:
                    conf_name = "東區 (Eastern Conference)" if conf == 'East' else "西區 (Western Conference)"
                    print(f"\n{conf_name}")
                    print(separator(BACKUP_COLUMNS))
                    
                    conf_teams = [row for row in rows if row[headers.index('Conference')] == conf]
                    conf_teams.sort(key=lambda x: x[headers.index('WinPCT')], reverse=True)
                    
                    print(format_table_row(['排名', '球隊', '勝', '敗', '勝率', '分區戰績', '主場', '客場'], BACKUP_COLUMNS))
                    print(separator(BACKUP_COLUMNS))
                    
                    for idx, team in enumerate(conf_teams, 1):
                        team_name = f"{team[headers.index('TeamCity')]} {team[headers.index('TeamName')]}"
                        wins = team[headers.index('WINS')]
                        losses = team[headers.index('LOSSES')]
                        win_pct = f"{team[headers.index('WinPCT')]:.3f}"
                        conf_record = team[headers.index('ConferenceRecord')]
                        home = team[headers.index('HOME')]
                        road = team[headers.index('ROAD')]
                        
                        print(format_table_row([idx, team_name, wins, losses, win_pct, conf_record, home, road], BACKUP_COLUMNS))
                
                return data
                
            except (TimeoutError, KeyboardInterrupt) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指數退避：2秒, 4秒
                    print(f"連線逾時，{wait_time}秒後重試...")
                    time.sleep(wait_time)
                else:
                    raise
        
    except ImportError:
        print("\n請安裝 nba_api 套件: pip install nba_api")
        return None
    except Exception as e:
        print(f"備用方案失敗: {type(e).__name__}: {e}")
        return None

if __name__ == "__main__":
    print("開始獲取 NBA 戰績表...\n")
    
    standings = None
    data_source = None
    
    # 按優先順序嘗試不同的 API
    print("═" * 100)
    print("第一步：嘗試 ESPN API (最穩定)")
    print("═" * 100)
    standings = fetch_nba_standings_espn()
    if standings is not None:
        data_source = "ESPN"
    
    if standings is None:
        print("\n" + "═" * 100)
        print("第二步：嘗試 nba_api (備用方案)")
        print("═" * 100)
        standings = fetch_nba_standings_backup(max_retries=2)
        if standings is not None:
            data_source = "NBA.com"
    
    if standings is None:
        print("\n" + "═" * 100)
        print("第三步：嘗試 NBA.com API")
        print("═" * 100)
        standings = fetch_nba_standings_nba_com()
        if standings is not None:
            data_source = "NBA.com"
    
    if standings is None:
        print("\n✗ 無法獲取數據。")
        print("\n請檢查：")
        print("1. 網路連接是否正常")
        print("2. 確保已安裝必要的套件：pip install nba_api requests")
        print("3. NBA API 服務是否可用")
    else:
        # 保存到日誌檔案
        save_to_log(standings, source=data_source or "NBA.com")
