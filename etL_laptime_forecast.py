import itertools
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import func
from sqlalchemy.orm import Session
from prophet import Prophet
from prophet.plot import add_changepoints_to_plot
from config import get_db_engine
from models import DimRace, FactLapTime, DimCircuit, DimSeason, FactWeather, FactPredictedLapTime, Base
from sqlalchemy import Column, Float, DateTime

def format_ms_to_laptime(ms):
    """
    Milliszekundum átalakítása F1-es MM:SS.ms formátumba (pl. 1:23.456)
    """
    minutes = int(ms // 60000)
    seconds = int((ms % 60000) // 1000)
    milliseconds = int(ms % 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"

def fetch_fastest_laps_with_weather(engine):
    """
    Lekérdezi az adatbázisból a leggyorsabb köridőket, kiegészítve az időjárással.
    """
    with Session(engine) as session:
        query = session.query(
            DimRace.date.label('race_date'),
            DimRace.circuit_id,
            DimSeason.year,
            DimSeason.era_name,
            func.min(FactLapTime.milliseconds).label('fastest_lap_ms'),
            func.avg(FactWeather.temperature).label('temperature'),
            func.avg(FactWeather.precipitation).label('precipitation'),
            func.avg(FactWeather.windspeed).label('windspeed')
        ).select_from(DimRace) \
         .join(FactLapTime, DimRace.race_id == FactLapTime.race_id) \
         .join(DimSeason, DimSeason.season_id == DimRace.season_id) \
         .outerjoin(FactWeather, DimRace.race_id == FactWeather.race_id) \
         .group_by(DimRace.date, DimRace.circuit_id, DimSeason.year, DimSeason.era_name) \
         .order_by(DimRace.date)
        
        df = pd.read_sql(query.statement, session.bind)
    return df

def preprocess_data(df):
    """
    Kiszámolja a Tempó Indexet és kezeli a hiányzó időjárási adatokat.
    """
    # Csak azokat a pályákat tartjuk meg, ahol legalább 3 futamot rendeztek
    track_counts = df['circuit_id'].value_counts()
    valid_tracks = track_counts[track_counts >= 3].index
    df = df[df['circuit_id'].isin(valid_tracks)].copy()

    # Pályánkénti átlagos leggyorsabb kör kiszámítása, hogy a tempó indexet normalizálni tudjuk
    track_avg = df.groupby('circuit_id')['fastest_lap_ms'].transform('mean')

    # Tempó Index: (Adott köridő / Pálya átlaga)
    # Minél kisebb az érték, annál gyorsabbak az autók.
    df['pace_index'] = df['fastest_lap_ms'] / track_avg
    
    # Ha nincs adat, feltételezzük, hogy nem esett, a hőmérsékletet/szelet pedig átlagoljuk
    df['precipitation'] = df['precipitation'].fillna(0)
    df['temperature'] = df['temperature'].fillna(df['temperature'].mean())
    df['windspeed'] = df['windspeed'].fillna(df['windspeed'].mean())
    
    df = df.rename(columns={'race_date': 'ds', 'pace_index': 'y'})
    df['ds'] = pd.to_datetime(df['ds'])
    
    return df

def train_and_forecast(df):
    """
    Prophet Modell tanítása és előrejelzés készítése.
    """
    print("Modell tanítása...")
    
    # A Prophet inicializálása
    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=1.0
    )
    
    # Külső regresszorok (időjárás) hozzáadása a modellhez
    model.add_regressor('precipitation')
    model.add_regressor('temperature')
    model.add_regressor('windspeed')
    
    model.fit(df)
    
    # Jövőbeli dataframe létrehozása következő 3 évre (156 hét)
    future = model.make_future_dataframe(periods=156, freq='W')
    
    # Jővőben ideális körülményeket feltételezünk: nincs csapadék, átlagos hőmérséklet és szél.
    future['precipitation'] = 0.0 
    future['temperature'] = df['temperature'].mean()
    future['windspeed'] = df['windspeed'].mean()
    
    # Historikus adatokat a valós értékekkel töltjük fel.
    future.loc[future['ds'].isin(df['ds']), 'precipitation'] = df['precipitation'].values
    future.loc[future['ds'].isin(df['ds']), 'temperature'] = df['temperature'].values
    future.loc[future['ds'].isin(df['ds']), 'windspeed'] = df['windspeed'].values

    # Előrejelzés
    forecast = model.predict(future)
    return model, forecast

def save_forecast_to_db(forecast, engine, df):
    """
    Elmenti a köridő predikciókat az adatbázisba.
    """
    print("Tempó predikciók visszatranszformálása valódi köridőkre...")
    
    # Pályák történelmi átlagai circuit_id szerint egy szótárba
    track_averages = df.groupby('circuit_id')['fastest_lap_ms'].mean().to_dict()
    
    # Csak a jövőbeli dátumokat prediktáljuk
    future_forecast = forecast[forecast['ds'] > df['ds'].max()][['ds', 'yhat']].copy()
    
    predicted_records = []
    
    # Minden jövőbeli időponthoz legeneráljuk az összes pálya várható idejét
    for (date, yhat), (c_id, avg_ms) in itertools.product(
        zip(future_forecast['ds'], future_forecast['yhat']), 
        track_averages.items()
    ):
        predicted_ms = yhat * avg_ms
        
        predicted_records.append({
            'ds': date,
            'circuit_id': c_id,
            'predicted_lap_ms': predicted_ms,
            'predicted_lap_formatted': format_ms_to_laptime(predicted_ms)
        })
    
    predicted_df = pd.DataFrame(predicted_records)
    
    # Tábla létrehozása és feltöltése
    Base.metadata.create_all(engine, tables=[FactPredictedLapTime.__table__])
    predicted_df.to_sql('fact_predicted_lap_times', con=engine, if_exists='replace', index=False)
    print(f"Sikeresen elmentve {len(predicted_df)} sor a PowerBI-nak!")

def visualize_results(model, forecast, df):
    """
    Predikciók ábrázolása.
    """
    fig = model.plot(forecast, figsize=(12, 6))
    add_changepoints_to_plot(fig.gca(), model, forecast)
    
    plt.title('F1 Tempó Index Idősoros Elemzése', fontsize=14)
    plt.xlabel('Dátum (Év)', fontsize=12)
    plt.ylabel('Tempó Index (Normalizált)', fontsize=12)
    
    plt.axvline(pd.to_datetime('2022-03-20'), color='green', linestyle='--', alpha=0.7)
    plt.text(pd.to_datetime('2022-06-01'), 1.25, 'Ground Effect Era', fontsize=10, color='green')

    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    engine = get_db_engine()
    
    print("Adatok lekérdezése (Tények + Időjárás)...")
    raw_df = fetch_fastest_laps_with_weather(engine)
    
    if raw_df.empty:
        print("Nem található adat. Futtasd le előbb az ETL szkripteket!")
    else:
        processed_df = preprocess_data(raw_df)
        model, forecast = train_and_forecast(processed_df)
        
        # Adatbázisba mentés a PowerBI-nak
        save_forecast_to_db(forecast, engine, processed_df)
        
        print("Vizualizációk generálása...")
        visualize_results(model, forecast, processed_df)