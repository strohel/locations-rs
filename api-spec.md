# Locations API specification
This document describes endpoints, parameters and responses for the Locations feature.

## Response Types
Base for all responses is the `CityResponse` entity. Kotlin and typescript definitions and json example follow.
```kotlin
// Kotlin
data class CityResponse(
    @ApiModelProperty(allowableValues = "ISO 3166-1 alpha-2 country code")
    val countryIso: String,
    val id: Long,
    val isFeatured: Boolean,
    val name: String,
    val regionName: String
)
```
```typescript
// TypeScript
type CityResponse = {
    countryIso: string, //ISO 3166-1 alpha-2 country code
    id: number,
    isFeatured: boolean,
    name: string,
    regionName: string
}
```
```json
// JSON example
{
    "countryIso": "CZ",
    "id": 12348923,
    "isFeatured": true,
    "name": "Brno",
    "regionName": "Brňenský kraj"
}
```
Note that the `name` and `regionName` properties will always be localized based on the given `language` request parameter.

When response code is anything other than `200` the response takes this shape:
```typescript
{
    message?: string // additional information when response code != 200
}
```

## Endpoints
All params are required unless specified otherwise by the `?` suffix.

### `GET` /city/v1/get
Returns a city of given id.
- query params
    - `id: integer`
    - `language: string` two-letter language code. (eg. `cs`)
- response codes
    - `404` City of given id does not exist.
- response
```typescript
CityResponse
```

### `GET` /city/v1/closest
Returns a single city that is closest to the coordinates. If coordinates are not given we fallback to IP geo-location to find the closest featured city.
- query params
    - `lat?: double` latitude in decimal degrees with `.` as decimal separator.
    - `lon?: double` longitude in decimal degrees with `.` as decimal separator.
    - `language: string` two-letter language code. (eg. `cs`)
- response codes
    - `400` Only one of `lat` and `lon` is given or one of them is out of bounds.
- response
```typescript
CityResponse
```

### `GET` /city/v1/associatedFeatured
For a given city id returns the closest featured city.
- query params
    - `id: integer`
    - `language: string` two-letter language code. (eg. `cs`)
- response codes
    - `404` City of given id does not exist.
- response
```typescript
CityResponse
```

### `GET` /city/v1/search
Returns list of matching cities. The response is limited to 10 cities and no pagination is provided. We believe we will return the correct result at the top. Otherwise the user have to provide more specific query string. The list is not guaranteed to be non-empty even with `200` response code.
- query params
    - `query: string` the search query
    - `language: string` two-letter language code. (eg. `cs`)
    - `countryIso?: string` ISO 3166-1 alpha-2 country code. Can be used to limit scope of the search to a given country.
- response codes
    - `400` - The query string is not given or is empty.
- response
```typescript
{   
    cities: [CityResponse], // array of up to 10 cities
}
```

### `GET` /city/v1/featured
Returns a list of all featured cities. Order of the list is indicative and should be translated to UI.
- query params
    - `language: string` two-letter language code. (eg. `cs`)
- response
```typescript
{   
    cities: [CityResponse], // array of all featured cities
}
```
