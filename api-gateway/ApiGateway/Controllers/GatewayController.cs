using Microsoft.AspNetCore.Mvc;
using System.Net.Http;
using System.Threading.Tasks;

namespace ApiGateway.Controllers
{
    [ApiController]
    [Route("[controller]")]
    public class GatewayController : ControllerBase
    {
        private readonly HttpClient _httpClient;

        public GatewayController(HttpClient httpClient)
        {
            _httpClient = httpClient;
        }

        /// <summary>
        /// Проксирует запрос к Service1
        /// </summary>
        /// <returns>Ответ от Service1</returns>
        [HttpGet("game_service/hello")]
        public async Task<IActionResult> GetService1Hello()
        {
            // Адрес Service1
            var service1Url = "http://localhost:5001/game_service/hello";

            // Отправка GET-запроса к Service1
            var response = await _httpClient.GetAsync(service1Url);

            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync();
                return Content(content, "application/json");
            }

            return StatusCode((int)response.StatusCode, "Error from Service1");
        }

        /// <summary>
        /// Проксирует запрос к Service2
        /// </summary>
        /// <returns>Ответ от Service2</returns>
        [HttpGet("lobby_service/hello")]
        public async Task<IActionResult> GetService2Hello()
        {
            // Адрес Service2
            var service2Url = "http://localhost:5002/lobby_service/hello";

            // Отправка GET-запроса к Service2
            var response = await _httpClient.GetAsync(service2Url);

            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync();
                return Content(content, "application/json");
            }

            return StatusCode((int)response.StatusCode, "Error from Service2");
        }
        
    }
}
