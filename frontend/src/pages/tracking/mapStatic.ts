// Statyczne dane mapy trackingu wg makiety Tracking.html (Claude Design):
// kluczowe porty, wszystkie terminale kontenerowe, magazyny docelowe,
// podświetlone kraje i polskie nazwy krajów + geometrie z world-atlas (50m — ostre granice
// przy zbliżeniu; 110m wyglądało przy zoomie jak łamana z kilku odcinków).
import { feature } from 'topojson-client'
import atlas from 'world-atlas/countries-50m.json'
import { WORLD_H, WORLD_W } from '../../worldmap'

export const px = (lon: number) => (lon + 180) / 360 * WORLD_W
export const py = (lat: number) => (90 - lat) / 180 * WORLD_H

export interface KeyPort {
  id: string
  name: string
  cc: string
  lon: number
  lat: number
  role: 'dest' | 'origin' | 'hub'
  /* przesunięcie etykiety (px ekranu) — ręczne rozmieszczenie z makiety */
  dx: number
  dy: number
  /* aliasy nazw z backendu (PORT_COORDS / vessel.near_port / location) */
  ais: string[]
}

// kluczowe porty tras (makieta PORTS) — liczby kontenerów/statków z realnych danych
export const KEY_PORTS: KeyPort[] = [
  { id: 'GDN', name: 'Gdańsk', cc: 'Polska', lon: 18.66, lat: 54.40, role: 'dest', dx: 78, dy: -34, ais: ['GDANSK', 'GDAŃSK'] },
  { id: 'GDY', name: 'Gdynia', cc: 'Polska', lon: 18.52, lat: 54.53, role: 'dest', dx: 78, dy: -62, ais: ['GDYNIA'] },
  { id: 'FXT', name: 'Felixstowe', cc: 'Wielka Brytania', lon: 1.33, lat: 51.95, role: 'hub', dx: -168, dy: -72, ais: ['FELIXSTOWE'] },
  { id: 'RTM', name: 'Rotterdam', cc: 'Holandia', lon: 4.42, lat: 51.92, role: 'hub', dx: -168, dy: -44, ais: ['ROTTERDAM'] },
  { id: 'ANR', name: 'Antwerpia', cc: 'Belgia', lon: 4.40, lat: 51.25, role: 'hub', dx: -168, dy: -16, ais: ['ANTWERP', 'ANTWERPIA'] },
  { id: 'HAM', name: 'Hamburg', cc: 'Niemcy', lon: 9.95, lat: 53.54, role: 'hub', dx: -168, dy: 12, ais: ['HAMBURG'] },
  { id: 'BRV', name: 'Bremerhaven', cc: 'Niemcy', lon: 8.54, lat: 53.55, role: 'hub', dx: -168, dy: 40, ais: ['BREMERHAVEN'] },
  { id: 'ALG', name: 'Algeciras', cc: 'Hiszpania', lon: -5.44, lat: 36.13, role: 'hub', dx: -136, dy: 22, ais: ['ALGECIRAS'] },
  { id: 'TNG', name: 'Tanger Med', cc: 'Maroko', lon: -5.50, lat: 35.89, role: 'hub', dx: -136, dy: 50, ais: ['TANGER MED', 'TANGER'] },
  { id: 'SIN2', name: 'Sines', cc: 'Iberia', lon: -8.87, lat: 37.95, role: 'hub', dx: -136, dy: -6, ais: ['SINES'] },
  { id: 'LEI', name: 'Leixões', cc: 'Iberia', lon: -8.70, lat: 41.18, role: 'hub', dx: -136, dy: -34, ais: ['LEIXOES', 'LEIXÕES'] },
  { id: 'PIR', name: 'Pireus', cc: 'Grecja', lon: 23.62, lat: 37.94, role: 'hub', dx: 44, dy: 26, ais: ['PIRAEUS', 'PIREUS'] },
  { id: 'JEA', name: 'Jebel Ali', cc: 'ZEA', lon: 55.06, lat: 25.01, role: 'hub', dx: 38, dy: -28, ais: ['JEBEL ALI'] },
  { id: 'CMB', name: 'Colombo', cc: 'Sri Lanka', lon: 79.85, lat: 6.95, role: 'hub', dx: -104, dy: 24, ais: ['COLOMBO'] },
  { id: 'SIN', name: 'Singapur', cc: 'Singapur', lon: 103.85, lat: 1.29, role: 'hub', dx: 52, dy: 44, ais: ['SINGAPORE', 'SINGAPUR'] },
  { id: 'PKG', name: 'Port Klang', cc: 'Malezja', lon: 101.36, lat: 3.00, role: 'hub', dx: -120, dy: 18, ais: ['PORT KLANG', 'KLANG'] },
  { id: 'SHA', name: 'Szanghaj', cc: 'Chiny', lon: 121.50, lat: 31.23, role: 'origin', dx: 60, dy: -28, ais: ['SHANGHAI'] },
  { id: 'NGB', name: 'Ningbo', cc: 'Chiny', lon: 121.55, lat: 29.87, role: 'origin', dx: 60, dy: 0, ais: ['NINGBO'] },
  { id: 'YTN', name: 'Yantian', cc: 'Chiny', lon: 114.27, lat: 22.57, role: 'origin', dx: 56, dy: 26, ais: ['YANTIAN', 'SHENZHEN', 'SHEKOU'] },
  { id: 'TAO', name: 'Qingdao', cc: 'Chiny', lon: 120.32, lat: 36.07, role: 'origin', dx: 60, dy: -56, ais: ['QINGDAO'] },
  { id: 'BUS', name: 'Busan', cc: 'Korea Płd.', lon: 129.07, lat: 35.10, role: 'origin', dx: 56, dy: -10, ais: ['BUSAN'] },
]

/* magazyny docelowe — hardkod z makiety; do podmiany na dane z systemu */
export interface Warehouse {
  id: string
  name: string
  company: string
  addr: string
  lon: number
  lat: number
  color: string
  dx: number
  dy: number
  /* port wejścia — początek odcinka lądowego (kreskowanego) */
  fromLon: number
  fromLat: number
  alt?: boolean
}
export const WAREHOUSES: Warehouse[] = [
  { id: 'RAD', name: 'MAG RADOM', company: 'Borealis', addr: 'ul. Magazynowa 1, 26-600 Radom, PL',
    lon: 21.147, lat: 51.402, color: '#e9a13b', dx: 74, dy: -30, fromLon: 18.66, fromLat: 54.40 },
  { id: 'DLT', name: 'MAG DLT', company: 'Acme · DLT', addr: 'ul. Logistyczna 2, 90-001 Łódź, PL',
    lon: 19.456, lat: 51.759, color: '#e0396b', dx: 74, dy: 26, fromLon: 18.66, fromLat: 54.40, alt: true },
  { id: 'PT', name: 'MAG IBERIA', company: 'Iberia', addr: 'Rua Logística 1, 7520-000 Sines, PT',
    lon: -8.78, lat: 37.99, color: '#7c3aed', dx: -150, dy: 46, fromLon: -8.87, fromLat: 37.95, alt: true },
]

/* wszystkie porty obsługujące kontenery (rozładunek / załadunek) — lista z makiety */
export const CPORTS: { name: string; cc: string; lon: number; lat: number }[] = ([
  ['Shanghai', 'CN', 121.50, 31.23], ['Ningbo', 'CN', 121.55, 29.87], ['Shenzhen', 'CN', 114.27, 22.57], ['Qingdao', 'CN', 120.32, 36.07],
  ['Guangzhou', 'CN', 113.44, 23.09], ['Tianjin', 'CN', 117.78, 38.98], ['Xiamen', 'CN', 118.08, 24.46], ['Dalian', 'CN', 121.65, 38.92],
  ['Hong Kong', 'HK', 114.13, 22.30], ['Kaohsiung', 'TW', 120.28, 22.61], ['Keelung', 'TW', 121.74, 25.14], ['Busan', 'KR', 129.07, 35.10],
  ['Incheon', 'KR', 126.60, 37.45], ['Gwangyang', 'KR', 127.75, 34.90], ['Tokyo', 'JP', 139.78, 35.62], ['Yokohama', 'JP', 139.67, 35.44],
  ['Nagoya', 'JP', 136.88, 35.05], ['Kobe', 'JP', 135.21, 34.67], ['Osaka', 'JP', 135.43, 34.64], ['Manila', 'PH', 120.95, 14.60],
  ['Laem Chabang', 'TH', 100.88, 13.08], ['Cai Mep', 'VN', 107.03, 10.53], ['Haiphong', 'VN', 106.72, 20.86],
  ['Tanjung Priok', 'ID', 106.88, -6.10], ['Tanjung Pelepas', 'MY', 103.55, 1.36], ['Singapur', 'SG', 103.85, 1.29],
  ['Port Klang', 'MY', 101.36, 3.00], ['Colombo', 'LK', 79.85, 6.95], ['Chennai', 'IN', 80.30, 13.10], ['Nhava Sheva', 'IN', 72.95, 18.95],
  ['Mundra', 'IN', 69.72, 22.75], ['Karachi', 'PK', 67.00, 24.80], ['Chittagong', 'BD', 91.80, 22.31],
  ['Jebel Ali', 'AE', 55.06, 25.01], ['Khalifa', 'AE', 54.65, 24.80], ['Dammam', 'SA', 50.20, 26.50], ['Jeddah', 'SA', 39.15, 21.48],
  ['Salalah', 'OM', 54.01, 16.94], ['Aqaba', 'JO', 35.00, 29.52], ['Djibouti', 'DJ', 43.14, 11.60],
  ['Rotterdam', 'NL', 4.42, 51.92], ['Antwerpia', 'BE', 4.40, 51.25], ['Hamburg', 'DE', 9.95, 53.54], ['Bremerhaven', 'DE', 8.54, 53.55],
  ['Felixstowe', 'GB', 1.33, 51.95], ['London Gateway', 'GB', 0.48, 51.51], ['Southampton', 'GB', -1.42, 50.89],
  ['Le Havre', 'FR', 0.13, 49.48], ['Dunkierka', 'FR', 2.36, 51.05], ['Zeebrugge', 'BE', 3.20, 51.33], ['Algeciras', 'ES', -5.44, 36.13],
  ['Valencia', 'ES', -0.32, 39.44], ['Barcelona', 'ES', 2.18, 41.35], ['Bilbao', 'ES', -3.05, 43.35], ['Las Palmas', 'ES', -15.41, 28.14],
  ['Genua', 'IT', 8.90, 44.40], ['La Spezia', 'IT', 9.84, 44.10], ['Gioia Tauro', 'IT', 15.90, 38.45], ['Pireus', 'GR', 23.62, 37.94],
  ['Ambarli', 'TR', 28.68, 40.97], ['Izmir', 'TR', 27.10, 38.43], ['Mersin', 'TR', 34.65, 36.79], ['Malta Freeport', 'MT', 14.53, 35.82],
  ['Konstanca', 'RO', 28.65, 44.17], ['Odessa', 'UA', 30.73, 46.48], ['Gdańsk', 'PL', 18.66, 54.40], ['Gdynia', 'PL', 18.52, 54.53],
  ['Świnoujście', 'PL', 14.27, 53.91], ['Kłajpeda', 'LT', 21.12, 55.70], ['Ryga', 'LV', 24.08, 57.00], ['Tallinn', 'EE', 24.80, 59.45],
  ['Sankt Petersburg', 'RU', 30.24, 59.90], ['Aarhus', 'DK', 10.22, 56.15], ['Göteborg', 'SE', 11.90, 57.70], ['Helsinki', 'FI', 25.19, 60.21],
  ['Sines', 'PT', -8.87, 37.95], ['Leixões', 'PT', -8.70, 41.18], ['Lizbona', 'PT', -9.17, 38.70], ['Tanger Med', 'MA', -5.50, 35.89],
  ['Casablanca', 'MA', -7.62, 33.60], ['Damietta', 'EG', 31.82, 31.42], ['Port Said', 'EG', 32.32, 31.25], ['Aleksandria', 'EG', 29.87, 31.20],
  ['Los Angeles', 'US', -118.26, 33.73], ['Long Beach', 'US', -118.21, 33.75], ['Oakland', 'US', -122.32, 37.80],
  ['Seattle', 'US', -122.34, 47.60], ['Vancouver', 'CA', -123.10, 49.29], ['Montreal', 'CA', -73.54, 45.55],
  ['New York', 'US', -74.15, 40.67], ['Savannah', 'US', -81.13, 32.08], ['Charleston', 'US', -79.93, 32.78], ['Norfolk', 'US', -76.33, 36.92],
  ['Houston', 'US', -95.28, 29.73], ['Miami', 'US', -80.17, 25.77], ['Kingston', 'JM', -76.85, 17.97], ['Colón', 'PA', -79.90, 9.36],
  ['Balboa', 'PA', -79.57, 8.94], ['Cartagena', 'CO', -75.52, 10.40], ['Callao', 'PE', -77.15, -12.05], ['San Antonio', 'CL', -71.62, -33.59],
  ['Buenos Aires', 'AR', -58.37, -34.58], ['Santos', 'BR', -46.30, -23.95], ['Paranaguá', 'BR', -48.51, -25.50],
  ['Rio de Janeiro', 'BR', -43.18, -22.89], ['Veracruz', 'MX', -96.13, 19.20], ['Manzanillo', 'MX', -104.31, 19.05],
  ['Lázaro Cárdenas', 'MX', -102.18, 17.94], ['Durban', 'ZA', 31.02, -29.86], ['Kapsztad', 'ZA', 18.42, -33.92],
  ['Ngqura', 'ZA', 25.65, -33.80], ['Lagos', 'NG', 3.37, 6.44], ['Lomé', 'TG', 1.28, 6.13], ['Abidżan', 'CI', -4.00, 5.29],
  ['Tema', 'GH', 0.00, 5.63], ['Dakar', 'SN', -17.42, 14.68], ['Mombasa', 'KE', 39.66, -4.05], ['Dar es Salaam', 'TZ', 39.29, -6.82],
  ['Luanda', 'AO', 13.23, -8.78], ['Pointe-Noire', 'CG', 11.85, -4.79], ['Walvis Bay', 'NA', 14.50, -22.95],
  ['Sydney', 'AU', 151.22, -33.98], ['Melbourne', 'AU', 144.90, -37.83], ['Brisbane', 'AU', 153.17, -27.38],
  ['Fremantle', 'AU', 115.75, -32.05], ['Auckland', 'NZ', 174.78, -36.84], ['Tauranga', 'NZ', 176.18, -37.64],
] as [string, string, number, number][]).map(([name, cc, lon, lat]) => ({ name, cc, lon, lat }))

const KEY_NAMES = new Set(KEY_PORTS.map(p => p.name))
export const CPORTS_MINOR = CPORTS.filter(p => !KEY_NAMES.has(p.name))

/* kraje podświetlone (Natural Earth numeric id) — makieta HL */
export const HL: Record<number, 'dest' | 'origin' | 'transit'> = {
  616: 'dest',
  156: 'origin', 458: 'origin', 702: 'origin',
  276: 'transit', 528: 'transit', 56: 'transit', 826: 'transit',
  724: 'transit', 620: 'transit', 504: 'transit', 710: 'transit',
  818: 'transit', 144: 'transit', 784: 'transit',
}
export const HL_FILL = { dest: 'rgba(255,209,102,.30)', origin: 'rgba(233,161,59,.24)', transit: 'rgba(110,168,245,.20)' }
export const HL_STROKE = { dest: 'rgba(255,220,140,.95)', origin: 'rgba(240,183,96,.8)', transit: 'rgba(126,178,247,.6)' }

/* polskie nazwy krajów (klucz: właściwość name z Natural Earth) — makieta PL_NAMES */
export const PL_NAMES: Record<string, string> = {
  Poland: 'Polska', Germany: 'Niemcy', Netherlands: 'Holandia', Belgium: 'Belgia',
  'United Kingdom': 'Wielka Brytania', Spain: 'Hiszpania', Portugal: 'Iberia', France: 'Francja', Italy: 'Włochy',
  Greece: 'Grecja', Turkey: 'Turcja', Morocco: 'Maroko', Egypt: 'Egipt', China: 'Chiny', Malaysia: 'Malezja', Singapore: 'Singapur',
  India: 'Indie', 'Sri Lanka': 'Sri Lanka', 'United Arab Emirates': 'ZEA', 'South Africa': 'RPA', 'Saudi Arabia': 'Arabia Saudyjska',
  Oman: 'Oman', Japan: 'Japonia', 'South Korea': 'Korea Południowa', Vietnam: 'Wietnam', Thailand: 'Tajlandia', Indonesia: 'Indonezja',
  Philippines: 'Filipiny', Taiwan: 'Tajwan', Pakistan: 'Pakistan', Bangladesh: 'Bangladesz', 'United States of America': 'Stany Zjednoczone',
  Canada: 'Kanada', Mexico: 'Meksyk', Brazil: 'Brazylia', Argentina: 'Argentyna', Chile: 'Chile', Peru: 'Peru', Colombia: 'Kolumbia',
  Panama: 'Panama', Australia: 'Australia', 'New Zealand': 'Nowa Zelandia', Russia: 'Rosja', Ukraine: 'Ukraina', Romania: 'Rumunia',
  Sweden: 'Szwecja', Norway: 'Norwegia', Finland: 'Finlandia', Denmark: 'Dania', Lithuania: 'Litwa', Latvia: 'Łotwa', Estonia: 'Estonia',
  Nigeria: 'Nigeria', Kenya: 'Kenia', Tanzania: 'Tanzania', Ghana: 'Ghana', Senegal: 'Senegal', Angola: 'Angola', Namibia: 'Namibia',
  Djibouti: 'Dżibuti', 'Ivory Coast': 'Wybrzeże Kości Słoniowej', "Côte d'Ivoire": 'Wybrzeże Kości Słoniowej',
  Togo: 'Togo', Israel: 'Izrael', Iran: 'Iran', Iraq: 'Irak',
  Afghanistan: 'Afganistan', Albania: 'Albania', Antarctica: 'Antarktyda', Armenia: 'Armenia', Azerbaijan: 'Azerbejdżan',
  Bahamas: 'Bahamy', Belize: 'Belize', Benin: 'Benin', Bhutan: 'Bhutan', Bolivia: 'Boliwia', 'Bosnia and Herz.': 'Bośnia i Hercegowina',
  Botswana: 'Botswana', Brunei: 'Brunei', Bulgaria: 'Bułgaria', 'Burkina Faso': 'Burkina Faso', Burundi: 'Burundi',
  Cambodia: 'Kambodża', Cameroon: 'Kamerun', 'Central African Rep.': 'Rep. Środkowoafrykańska', Chad: 'Czad', Congo: 'Kongo',
  'Dem. Rep. Congo': 'Dem. Rep. Konga', 'Costa Rica': 'Kostaryka', Croatia: 'Chorwacja', Cuba: 'Kuba', Cyprus: 'Cypr',
  'N. Cyprus': 'Cypr Północny', 'Dominican Rep.': 'Dominikana', Ecuador: 'Ekwador', 'El Salvador': 'Salwador',
  'Eq. Guinea': 'Gwinea Równikowa', Eritrea: 'Erytrea', Ethiopia: 'Etiopia', 'Falkland Is.': 'Falklandy', Fiji: 'Fidżi',
  'Fr. S. Antarctic Lands': 'Fr. Terytoria Poł.', Gabon: 'Gabon', Gambia: 'Gambia', Georgia: 'Gruzja', Greenland: 'Grenlandia',
  Guatemala: 'Gwatemala', Guinea: 'Gwinea', 'Guinea-Bissau': 'Gwinea Bissau', Guyana: 'Gujana', Haiti: 'Haiti', Honduras: 'Honduras',
  Iceland: 'Islandia', Jamaica: 'Jamajka', Kazakhstan: 'Kazachstan', Kosovo: 'Kosowo', Kuwait: 'Kuwejt', Kyrgyzstan: 'Kirgistan',
  Laos: 'Laos', Lebanon: 'Liban', Lesotho: 'Lesotho', Liberia: 'Liberia', Luxembourg: 'Luksemburg', Macedonia: 'Macedonia Północna',
  'North Macedonia': 'Macedonia Północna', Madagascar: 'Madagaskar', Malawi: 'Malawi', Mali: 'Mali', Mauritania: 'Mauretania',
  Moldova: 'Mołdawia', Mongolia: 'Mongolia', Montenegro: 'Czarnogóra', Mozambique: 'Mozambik', Myanmar: 'Mjanma', Nepal: 'Nepal',
  'New Caledonia': 'Nowa Kaledonia', Nicaragua: 'Nikaragua', Niger: 'Niger', 'North Korea': 'Korea Północna',
  Palestine: 'Palestyna', 'Papua New Guinea': 'Papua-Nowa Gwinea', Paraguay: 'Paragwaj', 'Puerto Rico': 'Portoryko',
  Qatar: 'Katar', Rwanda: 'Rwanda', 'S. Sudan': 'Sudan Południowy', Serbia: 'Serbia', 'Sierra Leone': 'Sierra Leone',
  Slovenia: 'Słowenia', 'Solomon Is.': 'Wyspy Salomona', Somalia: 'Somalia', Somaliland: 'Somaliland', Sudan: 'Sudan',
  Suriname: 'Surinam', Syria: 'Syria', Tajikistan: 'Tadżykistan', 'Timor-Leste': 'Timor Wschodni',
  'Trinidad and Tobago': 'Trynidad i Tobago', Turkmenistan: 'Turkmenistan', 'Türkiye': 'Turcja', Uganda: 'Uganda',
  Uruguay: 'Urugwaj', Uzbekistan: 'Uzbekistan', Vanuatu: 'Vanuatu', Venezuela: 'Wenezuela', 'W. Sahara': 'Sahara Zachodnia',
  Yemen: 'Jemen', Zambia: 'Zambia', Zimbabwe: 'Zimbabwe', eSwatini: 'Eswatini', Swaziland: 'Eswatini',
  Algeria: 'Algieria', Tunisia: 'Tunezja', Libya: 'Libia', Jordan: 'Jordania', Czechia: 'Czechy', Slovakia: 'Słowacja',
  Austria: 'Austria', Hungary: 'Węgry', Switzerland: 'Szwajcaria', Ireland: 'Irlandia', Belarus: 'Białoruś',
}

/* ---- geometrie krajów: topojson → path w TEJ SAMEJ liniowej projekcji co WORLD_PATH ---- */
export interface CountryShape {
  id: number
  name: string
  path: string
  /* środek największego poligonu (bbox center) — kotwica etykiety z nazwą */
  cx: number
  cy: number
}

type Ring = [number, number][]
// Ring przecinający antymerydian (Rosja, Fidżi, Antarktyda) rysowany liniową
// projekcją dawałby poziomy pas przez całą mapę. Normalizujemy: lon ujemny
// → +360 (ring ciągły na wschód od 180°) i rysujemy dwie kopie przesunięte
// o szerokość świata — część poza viewBoxem się nie pokazuje.
const crossesAM = (ring: Ring) => {
  let min = 999, max = -999
  for (const [lon] of ring) { if (lon < min) min = lon; if (lon > max) max = lon }
  return max - min > 180
}
const ringPath = (ring: Ring, shift = 0) =>
  'M' + ring.map(([lon, lat]) => `${(px(lon) + shift).toFixed(1)},${py(lat).toFixed(1)}`).join('L') + 'Z'
const ringPaths = (ring: Ring): string => {
  if (!crossesAM(ring)) return ringPath(ring)
  const norm: Ring = ring.map(([lon, lat]) => [lon < 0 ? lon + 360 : lon, lat])
  return ringPath(norm) + ringPath(norm, -WORLD_W)
}

function buildCountries(): CountryShape[] {
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const topo = atlas as any
  const fc = feature(topo, topo.objects.countries) as any
  return (fc.features as any[]).map(f => {
    const polys: Ring[][] = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
    let path = ''
    let best: Ring | null = null
    let bestArea = -1
    for (const poly of polys) {
      for (const ring of poly) path += ringPaths(ring)
      const outer: Ring = crossesAM(poly[0])
        ? poly[0].map(([lon, lat]) => [lon < 0 ? lon + 360 : lon, lat])
        : poly[0]
      let x0 = 999, x1 = -999, y0 = 999, y1 = -999
      for (const [lon, lat] of outer) {
        if (lon < x0) x0 = lon; if (lon > x1) x1 = lon
        if (lat < y0) y0 = lat; if (lat > y1) y1 = lat
      }
      const area = (x1 - x0) * (y1 - y0)
      if (area > bestArea) { bestArea = area; best = outer }
    }
    let cx = 0, cy = 0
    if (best) {
      let x0 = 999, x1 = -999, y0 = 999, y1 = -999
      for (const [lon, lat] of best) {
        if (lon < x0) x0 = lon; if (lon > x1) x1 = lon
        if (lat < y0) y0 = lat; if (lat > y1) y1 = lat
      }
      const lonC = (x0 + x1) / 2
      cx = px(lonC > 180 ? lonC - 360 : lonC); cy = py((y0 + y1) / 2)
    }
    return { id: +f.id, name: (f.properties && f.properties.name) || '', path, cx, cy }
  }).filter(c => c.path)
  /* eslint-enable @typescript-eslint/no-explicit-any */
}

export const COUNTRIES: CountryShape[] = buildCountries()

/* ---- dostawcy (fabryki) na mapie: lokalizacja bez geokodera ---- */

// większe miasta produkcyjne Chin — dopasowanie fragmentu adresu (LFA1 nie ma współrzędnych)
export const CN_CITIES: { name: string; lon: number; lat: number }[] = [
  { name: 'Shenzhen', lon: 114.06, lat: 22.54 }, { name: 'Ningbo', lon: 121.55, lat: 29.87 },
  { name: 'Shanghai', lon: 121.47, lat: 31.23 }, { name: 'Guangzhou', lon: 113.26, lat: 23.13 },
  { name: 'Yiwu', lon: 120.07, lat: 29.31 }, { name: 'Qingdao', lon: 120.38, lat: 36.07 },
  { name: 'Xiamen', lon: 118.09, lat: 24.48 }, { name: 'Dongguan', lon: 113.75, lat: 23.02 },
  { name: 'Foshan', lon: 113.12, lat: 23.02 }, { name: 'Suzhou', lon: 120.58, lat: 31.30 },
  { name: 'Hangzhou', lon: 120.16, lat: 30.29 }, { name: 'Tianjin', lon: 117.20, lat: 39.08 },
  { name: 'Wenzhou', lon: 120.70, lat: 28.00 }, { name: 'Shantou', lon: 116.68, lat: 23.35 },
  { name: 'Zhongshan', lon: 113.39, lat: 22.52 }, { name: 'Zhuhai', lon: 113.58, lat: 22.27 },
  { name: 'Huizhou', lon: 114.42, lat: 23.11 }, { name: 'Jiangmen', lon: 113.08, lat: 22.58 },
  { name: 'Quanzhou', lon: 118.68, lat: 24.87 }, { name: 'Fuzhou', lon: 119.30, lat: 26.08 },
  { name: 'Wuxi', lon: 120.30, lat: 31.57 }, { name: 'Changzhou', lon: 119.97, lat: 31.81 },
  { name: 'Nantong', lon: 120.89, lat: 31.98 }, { name: 'Taizhou', lon: 121.42, lat: 28.66 },
  { name: 'Jinhua', lon: 119.65, lat: 29.08 }, { name: 'Shaoxing', lon: 120.58, lat: 30.00 },
  { name: 'Nanjing', lon: 118.80, lat: 32.06 }, { name: 'Hefei', lon: 117.23, lat: 31.82 },
  { name: 'Wuhan', lon: 114.31, lat: 30.59 }, { name: 'Chengdu', lon: 104.07, lat: 30.57 },
  { name: 'Chongqing', lon: 106.55, lat: 29.56 }, { name: 'Zhengzhou', lon: 113.63, lat: 34.75 },
  { name: 'Jinan', lon: 117.12, lat: 36.65 }, { name: 'Yantai', lon: 121.45, lat: 37.46 },
  { name: 'Weifang', lon: 119.16, lat: 36.71 }, { name: 'Dalian', lon: 121.61, lat: 38.91 },
  { name: 'Beijing', lon: 116.40, lat: 39.90 }, { name: 'Hong Kong', lon: 114.17, lat: 22.32 },
]
// dłuższe nazwy najpierw — "Zhongshan" ma wygrać zanim trafi krótszy fragment
const CN_CITIES_SORTED = [...CN_CITIES].sort((a, b) => b.name.length - a.name.length)

// ISO2 (LFA1 LAND1) → numeryczne id Natural Earth — fallback: centroid kraju
export const ISO2_COUNTRY_ID: Record<string, number> = {
  CN: 156, TW: 158, HK: 156, IN: 356, VN: 704, TH: 764, KR: 410, JP: 392, MY: 458,
  SG: 702, ID: 360, PK: 586, BD: 50, TR: 792, DE: 276, IT: 380, ES: 724, PT: 620,
  NL: 528, BE: 56, GB: 826, FR: 250, PL: 616, CZ: 203, SK: 703, HU: 348, AT: 40,
  CH: 756, SE: 752, DK: 208, LT: 440, LV: 428, EE: 233, UA: 804, RO: 642, GR: 300,
  BG: 100, US: 840, MX: 484, BR: 76, EG: 818, MA: 504, ZA: 710, AE: 784, SA: 682,
}

/** Pozycja dostawcy na mapie (px świata): miasto z adresu (tylko Chiny/HK/TW),
    fallback centroid kraju z topojson, brak dopasowania → null. */
export function supplierCoords(address: string, country: string):
    { x: number; y: number; city: string | null } | null {
  const cc = (country || '').trim().toUpperCase()
  if (!cc || cc === 'CN' || cc === 'HK' || cc === 'TW') {
    const a = (address || '').toLowerCase()
    const hit = CN_CITIES_SORTED.find(c => a.includes(c.name.toLowerCase()))
    if (hit) return { x: px(hit.lon), y: py(hit.lat), city: hit.name }
  }
  const id = ISO2_COUNTRY_ID[cc]
  const c = id != null ? COUNTRIES.find(k => k.id === id) : undefined
  return c ? { x: c.cx, y: c.cy, city: null } : null
}

/* deterministyczne kolory państw: id → jedna z 12 stonowanych barw (niska alpha,
   żeby nie zabić czytelności warstw na ciemnej mapie) — wspólne dla mapy 2D i globusa 3D */
export const COUNTRY_PALETTE = [
  'rgba(110,168,245,.16)', 'rgba(125,211,192,.16)', 'rgba(233,161,59,.14)',
  'rgba(224,122,166,.15)', 'rgba(167,139,250,.15)', 'rgba(148,190,110,.16)',
  'rgba(96,205,228,.15)', 'rgba(240,171,120,.15)', 'rgba(190,160,220,.14)',
  'rgba(120,180,160,.16)', 'rgba(210,150,140,.15)', 'rgba(140,160,230,.15)',
]
/* Number.isFinite: Somaliland/Kosowo nie mają numerycznego id (NaN → czarny fill) */
export const countryFill = (c: { id: number; name: string }) =>
  COUNTRY_PALETTE[(Number.isFinite(c.id) ? Math.abs(c.id) : c.name.length) % COUNTRY_PALETTE.length]

// Ląd sklejony z poligonów krajów (każdy ring domknięty, poprawne wypełnienie).
// WORLD_PATH z worldmap.ts ma zepsute nawinięcia ringów — z regułą nonzero
// zalewał Atlantyk „lądem" (blada mapa na prodzie), więc go tu nie używamy.
export const LAND_PATH: string = COUNTRIES.map(c => c.path).join('')
