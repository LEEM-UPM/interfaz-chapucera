# Interfaz LEEM

Interfaz gráfica para control y monitoreo de sensores LEEM.

## Características

- Conexión serial a dispositivos LEEM
- Visualización en tiempo real de 10 termopares (Tp1-Tp10)
- Monitoreo de presión (Ps) y contador (N)
- Gráficas en tiempo real de presión, N y temperatura
- Sistema de ignición con cuenta regresiva de 10 segundos
- Registro de datos en archivo de texto
- Cálculo de frecuencia de recepción de datos (Hz)

## Requisitos

- Python 3.x
- pyserial
- matplotlib
- numpy
- pandas

## Instalación

```bash
pip install pyserial matplotlib numpy pandas
```

## Uso

```bash
python LEEM_interface_app.py
```

## Comandos seriales

- `0x01`: Solicitar datos de sensores
- `0x02`: Iniciar medición continua
- `0x03`: Detener medición
- `0x04`: Comando de ignición

## Interfaz

- **Conectar**: Establece conexión serial
- **START/STOP**: Inicia/detiene la medición y graficado
- **GET VALUE**: Solicita una lectura de sensores
- **IGNITAR**: Inicia cuenta regresiva de 10s y envía comando de ignición
